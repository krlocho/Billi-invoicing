"""Build evaluation datasets from existing reconciliations.

Given a reconciliation_id, snapshot:
  - input: bank transactions + reservations as they were submitted
  - ground truth: confirmed matches (status='confirmed' is the gold standard)

Pending matches are excluded from the gold set (user has not reviewed
them yet); rejected matches contribute as negative pairs (predictions
of those should count against precision).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.matching.engine import ReservationData, TransactionData
from src.models.bank_transaction import BankTransaction
from src.models.channel import Channel
from src.models.channel_reservation import ChannelReservation
from src.models.evaluation_label import EvaluationLabel
from src.models.reconciliation import (
    MatchReservation,
    Reconciliation,
    ReconciliationMatch,
)


@dataclass
class GroundTruthMatch:
    bank_transaction_id: str
    reservation_ids: frozenset[str]
    status: str  # confirmed | pending | rejected


@dataclass
class EvaluationDataset:
    reconciliation_id: str
    tenant_id: uuid.UUID
    transactions: list[TransactionData]
    reservations: list[ReservationData]
    truth: list[GroundTruthMatch]

    @property
    def positive_truth(self) -> list[GroundTruthMatch]:
        return [t for t in self.truth if t.status == "confirmed"]

    @property
    def negative_truth(self) -> list[GroundTruthMatch]:
        return [t for t in self.truth if t.status == "rejected"]


def _channel_code(db: Session, channel_id) -> str | None:
    if not channel_id:
        return None
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    return ch.code if ch else None


def build_dataset(
    db: Session,
    reconciliation_id: str,
    truth_source: str = "system",
) -> EvaluationDataset:
    """Build an evaluation dataset.

    truth_source:
      - "system":   ground truth = matches the system produced + user
                    confirmed/rejected (selection-biased, but available
                    as soon as the user reviews the matches).
      - "manual":   ground truth = independent labels from the labeling
                    UI (unbiased, requires the user to label first).
    """
    rec = db.query(Reconciliation).filter(
        Reconciliation.id == uuid.UUID(reconciliation_id)
    ).first()
    if not rec:
        raise ValueError(f"Reconciliation {reconciliation_id} not found")

    bank_txs = (
        db.query(BankTransaction)
        .filter(BankTransaction.upload_id == rec.bank_upload_id)
        .order_by(BankTransaction.transaction_date.asc())
        .all()
    )

    truth: list[GroundTruthMatch] = []
    res_ids: set = set()

    if truth_source == "manual":
        labels = (
            db.query(EvaluationLabel)
            .filter(EvaluationLabel.reconciliation_id == rec.id)
            .all()
        )
        for l in labels:
            rids = [str(r) for r in (l.reservation_ids or [])]
            res_ids.update(rids)
            truth.append(GroundTruthMatch(
                bank_transaction_id=str(l.bank_transaction_id),
                reservation_ids=frozenset(rids),
                # Map labeling status to truth status: 'match' is the gold
                # positive set; 'no_match' is the gold negative set.
                status="confirmed" if l.label_type == "match" else "rejected",
            ))
        # Reservations: every reservation referenced by any label, plus any
        # reservation of this tenant we know about (so the strategies that
        # consume the dataset still see the full candidate pool).
        all_reservations = (
            db.query(ChannelReservation)
            .filter(ChannelReservation.tenant_id == rec.tenant_id)
            .all()
        )
        reservations = all_reservations
    elif truth_source == "system":
        matches = (
            db.query(ReconciliationMatch)
            .filter(ReconciliationMatch.reconciliation_id == rec.id)
            .all()
        )
        for m in matches:
            rids = [
                mr.reservation_id
                for mr in db.query(MatchReservation)
                .filter(MatchReservation.match_id == m.id)
                .all()
            ]
            res_ids.update(rids)
            truth.append(GroundTruthMatch(
                bank_transaction_id=str(m.bank_transaction_id),
                reservation_ids=frozenset(str(r) for r in rids),
                status=m.status,
            ))
        reservations = (
            db.query(ChannelReservation)
            .filter(ChannelReservation.id.in_(res_ids))
            .all()
            if res_ids
            else []
        )
    else:
        raise ValueError(f"Unknown truth_source: {truth_source}")

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
            channel_code=_channel_code(db, r.channel_id),
            payout_ref=r.payout_ref,
        )
        for r in reservations
    ]

    return EvaluationDataset(
        reconciliation_id=reconciliation_id,
        tenant_id=rec.tenant_id,
        transactions=tx_data,
        reservations=res_data,
        truth=truth,
    )
