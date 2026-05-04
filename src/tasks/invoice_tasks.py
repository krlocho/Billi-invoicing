import logging
import uuid
from datetime import date

from src.celery_app import celery
from src.config import settings
from src.database import SessionLocal
from src.invoice_gen.generator import generate_invoice_pdf
from src.models.bank_transaction import BankTransaction
from src.models.channel_reservation import ChannelReservation
from src.models.invoice import Invoice
from src.models.reconciliation import MatchReservation, ReconciliationMatch
from src.models.tenant import Tenant

logger = logging.getLogger(__name__)


def _generate_invoices_sync(tenant_id: str, reconciliation_id: str, match_ids: list[str] | None):
    """Generate invoice PDFs for confirmed reconciliation matches (synchronous)."""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).first()
        if not tenant:
            logger.error(f"Tenant {tenant_id} not found")
            return

        # Get confirmed matches joined with bank transactions, ordered by tx date
        # (Spain legal requirement: invoice numbering must follow chronological order)
        query = (
            db.query(ReconciliationMatch, BankTransaction)
            .join(BankTransaction, ReconciliationMatch.bank_transaction_id == BankTransaction.id)
            .filter(
                ReconciliationMatch.reconciliation_id == uuid.UUID(reconciliation_id),
                ReconciliationMatch.status == "confirmed",
            )
            .order_by(BankTransaction.transaction_date.asc(), BankTransaction.id.asc())
        )
        if match_ids:
            query = query.filter(ReconciliationMatch.id.in_([uuid.UUID(mid) for mid in match_ids]))

        match_rows = query.all()

        # Determine next invoice number — find highest existing for the year
        # so newly generated invoices continue the sequence chronologically.
        existing_invoices = (
            db.query(Invoice)
            .filter(Invoice.tenant_id == uuid.UUID(tenant_id))
            .all()
        )
        # Use earliest tx date of this batch to decide year of issuance
        batch_year = match_rows[0][1].transaction_date.year if match_rows else date.today().year
        last_num = 0
        last_issue_date_for_year: date | None = None
        for inv in existing_invoices:
            if inv.invoice_number.startswith(f"{batch_year}/"):
                try:
                    n = int(inv.invoice_number.split("/")[-1])
                    if n > last_num:
                        last_num = n
                        last_issue_date_for_year = inv.issue_date
                except ValueError:
                    pass

        # Guard: any new invoice's issue_date must be >= the last issued one for that year.
        # If a confirmed match has an earlier bank tx date, refuse to violate ordering.
        if last_issue_date_for_year is not None and match_rows:
            earliest_in_batch = match_rows[0][1].transaction_date
            if earliest_in_batch < last_issue_date_for_year:
                logger.error(
                    f"Refusing to generate invoices: earliest tx in batch ({earliest_in_batch}) "
                    f"is before last issued invoice date ({last_issue_date_for_year}) for year {batch_year}"
                )
                return

        generated = 0
        for match, bank_tx in match_rows:
            # Get reservations for this match, ordered by checkout_date for stability
            match_res = (
                db.query(MatchReservation, ChannelReservation)
                .join(ChannelReservation, MatchReservation.reservation_id == ChannelReservation.id)
                .filter(MatchReservation.match_id == match.id)
                .order_by(ChannelReservation.checkout_date.asc(), ChannelReservation.id.asc())
                .all()
            )

            issue_date_value = bank_tx.transaction_date

            for _mr, reservation in match_res:
                # Check if invoice already exists
                existing = db.query(Invoice).filter(
                    Invoice.reservation_id == reservation.id
                ).first()
                if existing:
                    continue

                last_num += 1
                invoice_number = f"{issue_date_value.year}/{last_num:04d}"

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

                try:
                    pdf_path = generate_invoice_pdf(
                        invoice_number=invoice_number,
                        hotel_name=tenant.name,
                        hotel_tax_id=tenant.tax_id or "N/A",
                        hotel_address=tenant.address or "",
                        guest_name=reservation.guest_name or "N/A",
                        guest_tax_id=None,
                        issue_date=issue_date_value,
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
                except OSError as pdf_err:
                    # PDF rendering env issue (e.g. WeasyPrint missing libs);
                    # persist the invoice record so accounting state is correct
                    # and the PDF can be regenerated later.
                    logger.warning(f"PDF generation failed for {invoice_number}: {pdf_err}")
                    pdf_path = None

                invoice = Invoice(
                    tenant_id=uuid.UUID(tenant_id),
                    invoice_number=invoice_number,
                    reservation_id=reservation.id,
                    match_id=match.id,
                    guest_name=reservation.guest_name,
                    issue_date=issue_date_value,
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
        raise
    finally:
        db.close()


@celery.task(bind=True, max_retries=2)
def generate_invoices_task(self, tenant_id: str, reconciliation_id: str, match_ids: list[str] | None):
    """Celery wrapper (kept for production use)."""
    try:
        _generate_invoices_sync(tenant_id, reconciliation_id, match_ids)
    except Exception as e:
        raise self.retry(exc=e, countdown=60)
