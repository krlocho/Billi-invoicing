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


def build_dataset(db: Session, reconciliation_id: str) -> EvaluationDataset:
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

    # Reservations linked to any match in this reconciliation, plus any other
    # reservations of this tenant that were unreconciled at the time. We
    # approximate the input snapshot as: every reservation referenced by a
    # match (in any state). For unmatched reservations we have no good signal.
    matches = (
        db.query(ReconciliationMatch)
        .filter(ReconciliationMatch.reconciliation_id == rec.id)
        .all()
    )
    res_ids: set = set()
    truth: list[GroundTruthMatch] = []
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
