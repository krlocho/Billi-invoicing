import logging
import uuid
from datetime import datetime, timezone

from src.celery_app import celery
from src.database import SessionLocal
from src.matching.engine import MatchResult, ReservationData, TransactionData, run_matching
from src.models.bank_transaction import BankTransaction
from src.models.channel_reservation import ChannelReservation
from src.models.feedback import ReconciliationFeedback
from src.models.reconciliation import MatchReservation, Reconciliation, ReconciliationMatch

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=2)
def run_reconciliation(self, reconciliation_id: str, bank_upload_id: str, channel_upload_ids: list[str]):
    """Run the full reconciliation pipeline."""
    db = SessionLocal()
    try:
        rec = db.query(Reconciliation).filter(
            Reconciliation.id == uuid.UUID(reconciliation_id)
        ).first()
        if not rec:
            logger.error(f"Reconciliation {reconciliation_id} not found")
            return

        rec.status = "running"
        rec.started_at = datetime.now(timezone.utc)
        db.commit()

        # Load bank transactions
        bank_txs = db.query(BankTransaction).filter(
            BankTransaction.upload_id == uuid.UUID(bank_upload_id),
            BankTransaction.is_reconciled == False,
        ).all()

        # Load channel reservations
        reservations = []
        for cuid in channel_upload_ids:
            res = db.query(ChannelReservation).filter(
                ChannelReservation.upload_id == uuid.UUID(cuid),
                ChannelReservation.is_reconciled == False,
            ).all()
            reservations.extend(res)

        rec.total_transactions = len(bank_txs)

        if not bank_txs or not reservations:
            rec.status = "completed"
            rec.unmatched = len(bank_txs)
            rec.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        # Prepare data for matching engine
        tx_data = [
            TransactionData(
                id=str(tx.id),
                date=str(tx.transaction_date),
                description=tx.description,
                amount=float(tx.amount),
            )
            for tx in bank_txs
        ]

        res_data = [
            ReservationData(
                id=str(r.id),
                reservation_id=r.reservation_id,
                guest_name=r.guest_name,
                checkin_date=str(r.checkin_date) if r.checkin_date else None,
                checkout_date=str(r.checkout_date) if r.checkout_date else None,
                gross_amount=float(r.gross_amount) if r.gross_amount else None,
                net_amount=float(r.net_amount) if r.net_amount else None,
                channel_code=_get_channel_code(db, r.channel_id),
            )
            for r in reservations
        ]

        # Load feedback examples for few-shot learning
        feedback_examples = _load_feedback_examples(db, rec.tenant_id)

        # Build tenant-specific context (variable commissions, taxes, etc.)
        tenant_context = _build_tenant_context(db, rec.tenant_id)

        # Run matching with RAG + tiered LLM
        matches: list[MatchResult] = run_matching(
            tx_data, res_data, feedback_examples, tenant_context
        )

        # Store results
        matched_auto = 0
        matched_manual = 0
        for match in matches:
            rec_match = ReconciliationMatch(
                reconciliation_id=rec.id,
                bank_transaction_id=uuid.UUID(match.bank_transaction_id),
                confidence_score=match.confidence_score,
                confidence_tier=match.confidence_tier,
                amount_difference=match.amount_difference,
                match_type=match.match_type,
                status="confirmed" if match.confidence_tier == "HIGH" else "pending",
                match_details={
                    "reasoning": match.reasoning,
                    **match.details,
                },
            )
            db.add(rec_match)
            db.flush()

            for rid in match.reservation_ids:
                db.add(MatchReservation(match_id=rec_match.id, reservation_id=uuid.UUID(rid)))

            if match.confidence_tier == "HIGH":
                matched_auto += 1
                # Mark as reconciled
                db.query(BankTransaction).filter(
                    BankTransaction.id == uuid.UUID(match.bank_transaction_id)
                ).update({"is_reconciled": True})
                for rid in match.reservation_ids:
                    db.query(ChannelReservation).filter(
                        ChannelReservation.id == uuid.UUID(rid)
                    ).update({"is_reconciled": True})
            else:
                matched_manual += 1

        matched_tx_ids = {m.bank_transaction_id for m in matches}
        unmatched = len(bank_txs) - len(matched_tx_ids)

        rec.matched_auto = matched_auto
        rec.matched_manual = matched_manual
        rec.unmatched = unmatched
        rec.status = "completed"
        rec.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            f"Reconciliation {reconciliation_id} completed: "
            f"{matched_auto} auto, {matched_manual} manual, {unmatched} unmatched"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Reconciliation failed: {e}")
        rec = db.query(Reconciliation).filter(
            Reconciliation.id == uuid.UUID(reconciliation_id)
        ).first()
        if rec:
            rec.status = "failed"
            db.commit()
        raise self.retry(exc=e, countdown=120)
    finally:
        db.close()


def _build_tenant_context(db, tenant_id) -> str:
    """Build tenant-specific context for LLM — variable commissions, taxes, bank formats.

    This is what makes the system work for ANY hotel, not just one.
    Each hotel has different commission rates, tax regimes, properties, etc.
    """
    from src.models.channel import Channel
    from src.models.tenant import Tenant

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    channels = db.query(Channel).filter(Channel.tenant_id == tenant_id).all()

    lines = []
    if tenant:
        tax_info = tenant.settings.get("tax_type", "IGIC")
        tax_rate = tenant.settings.get("tax_rate", 7.0)
        lines.append(f"Hotel: {tenant.name}. Tax: {tax_info} {tax_rate}%.")
        if tenant.settings.get("country"):
            lines.append(f"Country: {tenant.settings['country']}.")

    if channels:
        lines.append("Channel commissions:")
        for ch in channels:
            config = ch.commission_config or {}
            base = config.get("base_rate", "unknown")
            psf = config.get("psf_rate", 0)
            patterns = ch.bank_description_patterns or []
            line = f"  {ch.name}: {float(base)*100 if isinstance(base, (int,float)) else base}%"
            if psf:
                line += f" + {float(psf)*100}% PSF"
            if patterns:
                line += f" (bank pattern: {patterns[0]})"
            lines.append(line)
    else:
        # No channels configured — tell the LLM commissions are variable
        lines.append(
            "No channel commissions configured. "
            "Commissions vary by channel, program and contract: "
            "Booking.com 15-30% + optional PSF, Airbnb 3-16%, Expedia 15-25%, "
            "Stripe 1.4-2.9% (own website). "
            "Infer the actual rate from the difference between gross reservation amounts and bank payment."
        )

    return " ".join(lines) if lines else ""


def _get_channel_code(db, channel_id) -> str | None:
    if not channel_id:
        return None
    from src.models.channel import Channel
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    return ch.code if ch else None


def _load_feedback_examples(db, tenant_id) -> list[dict]:
    """Load confirmed match examples for few-shot learning."""
    feedbacks = (
        db.query(ReconciliationFeedback)
        .filter(ReconciliationFeedback.action == "confirmed")
        .order_by(ReconciliationFeedback.created_at.desc())
        .limit(20)
        .all()
    )

    examples = []
    for fb in feedbacks:
        match = db.query(ReconciliationMatch).filter(
            ReconciliationMatch.id == fb.match_id
        ).first()
        if match and match.match_details:
            tx = db.query(BankTransaction).filter(
                BankTransaction.id == match.bank_transaction_id
            ).first()
            if tx:
                examples.append({
                    "bank_description": tx.description,
                    "bank_amount": float(tx.amount),
                    "match_details": match.match_details,
                    "was_correct": True,
                })

    return examples
