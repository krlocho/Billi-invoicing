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

        # Run matching
        matches: list[MatchResult] = run_matching(tx_data, res_data, feedback_examples)

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
