import logging
import uuid
from datetime import date

from src.celery_app import celery
from src.config import settings
from src.database import SessionLocal
from src.invoice_gen.generator import generate_invoice_pdf
from src.models.channel_reservation import ChannelReservation
from src.models.invoice import Invoice
from src.models.reconciliation import MatchReservation, ReconciliationMatch
from src.models.tenant import Tenant

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=2)
def generate_invoices_task(self, tenant_id: str, reconciliation_id: str, match_ids: list[str] | None):
    """Generate invoice PDFs for confirmed reconciliation matches."""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).first()
        if not tenant:
            logger.error(f"Tenant {tenant_id} not found")
            return

        # Get confirmed matches
        query = db.query(ReconciliationMatch).filter(
            ReconciliationMatch.reconciliation_id == uuid.UUID(reconciliation_id),
            ReconciliationMatch.status == "confirmed",
        )
        if match_ids:
            query = query.filter(ReconciliationMatch.id.in_([uuid.UUID(mid) for mid in match_ids]))

        matches = query.all()

        # Get next invoice number
        last_invoice = (
            db.query(Invoice)
            .filter(Invoice.tenant_id == uuid.UUID(tenant_id))
            .order_by(Invoice.created_at.desc())
            .first()
        )
        year = date.today().year
        if last_invoice and last_invoice.invoice_number.startswith(str(year)):
            last_num = int(last_invoice.invoice_number.split("/")[-1])
        else:
            last_num = 0

        generated = 0
        for match in matches:
            # Get reservations for this match
            match_res = db.query(MatchReservation).filter(
                MatchReservation.match_id == match.id
            ).all()

            for mr in match_res:
                reservation = db.query(ChannelReservation).filter(
                    ChannelReservation.id == mr.reservation_id
                ).first()
                if not reservation:
                    continue

                # Check if invoice already exists
                existing = db.query(Invoice).filter(
                    Invoice.reservation_id == reservation.id
                ).first()
                if existing:
                    continue

                last_num += 1
                invoice_number = f"{year}/{last_num:04d}"

                # Tax rate from tenant settings (IGIC, IVA, VAT, etc.)
                tenant_tax_rate = tenant.settings.get("tax_rate", settings.default_tax_rate)
                tax_rate = float(tenant_tax_rate)
                gross = float(reservation.gross_amount or 0)
                subtotal = gross / (1 + tax_rate / 100)
                tax_amount = gross - subtotal

                nights = reservation.nights or 1
                unit_price = subtotal / nights if nights > 0 else subtotal

                line_items = [
                    {
                        "description": f"Alojamiento - {reservation.room_type or 'Habitación'}",
                        "quantity": nights,
                        "unit_price": f"{unit_price:,.2f}",
                        "amount": f"{subtotal:,.2f}",
                    }
                ]

                pdf_path = generate_invoice_pdf(
                    invoice_number=invoice_number,
                    hotel_name=tenant.name,
                    hotel_tax_id=tenant.tax_id or "N/A",
                    hotel_address=tenant.address or "",
                    guest_name=reservation.guest_name or "N/A",
                    guest_tax_id=None,
                    issue_date=date.today(),
                    checkin_date=reservation.checkin_date,
                    checkout_date=reservation.checkout_date,
                    line_items=line_items,
                    subtotal=subtotal,
                    tax_rate=tax_rate,
                    tax_amount=tax_amount,
                    total=gross,
                    currency=reservation.currency,
                    tax_name=tenant.settings.get("tax_type", settings.default_tax_type),
                )

                invoice = Invoice(
                    tenant_id=uuid.UUID(tenant_id),
                    invoice_number=invoice_number,
                    reservation_id=reservation.id,
                    match_id=match.id,
                    guest_name=reservation.guest_name,
                    issue_date=date.today(),
                    checkin_date=reservation.checkin_date,
                    checkout_date=reservation.checkout_date,
                    subtotal=subtotal,
                    tax_rate=tax_rate,
                    tax_amount=tax_amount,
                    total=gross,
                    currency=reservation.currency,
                    pdf_path=pdf_path,
                    status="issued",
                    line_items=line_items,
                )
                db.add(invoice)
                generated += 1

        db.commit()
        logger.info(f"Generated {generated} invoices for reconciliation {reconciliation_id}")

    except Exception as e:
        db.rollback()
        logger.error(f"Invoice generation failed: {e}")
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()
