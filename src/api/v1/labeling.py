"""Independent labeling endpoints — manually-curated ground truth.

CRITICAL: Never include the system's matches in any response here.
Labellers must work blind so the resulting labels are unbiased.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import get_db
from src.models.bank_transaction import BankTransaction
from src.models.channel import Channel
from src.models.channel_reservation import ChannelReservation
from src.models.evaluation_label import EvaluationLabel
from src.models.reconciliation import Reconciliation
from src.models.user import User
from src.schemas.labeling import (
    LabelCreate,
    LabelEntry,
    LabelingDataset,
    LabelingProgress,
    LabelingReservation,
    LabelingTransaction,
)

router = APIRouter()


def _ensure_owned(db: Session, reconciliation_id: str, user: User) -> Reconciliation:
    rec = db.query(Reconciliation).filter(
        Reconciliation.id == uuid.UUID(reconciliation_id),
        Reconciliation.tenant_id == user.tenant_id,
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    return rec


@router.get("/{reconciliation_id}/dataset", response_model=LabelingDataset)
def get_dataset(
    reconciliation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns raw bank txs + reservations, NO predictions."""
    rec = _ensure_owned(db, reconciliation_id, user)

    txs = (
        db.query(BankTransaction)
        .filter(BankTransaction.upload_id == rec.bank_upload_id)
        .order_by(BankTransaction.transaction_date.asc(), BankTransaction.id.asc())
        .all()
    )

    # Reservations: every reservation in the tenant that could plausibly be
    # in scope for this reconciliation. Conservatively, we surface all
    # reservations of this tenant — labellers can ignore the irrelevant ones.
    reservations = (
        db.query(ChannelReservation, Channel)
        .outerjoin(Channel, ChannelReservation.channel_id == Channel.id)
        .filter(ChannelReservation.tenant_id == user.tenant_id)
        .order_by(ChannelReservation.checkout_date.asc().nullslast(), ChannelReservation.id.asc())
        .all()
    )

    return LabelingDataset(
        reconciliation_id=str(rec.id),
        transactions=[
            LabelingTransaction(
                id=str(t.id),
                transaction_date=t.transaction_date,
                description=t.description,
                amount=float(t.amount),
            )
            for t in txs
        ],
        reservations=[
            LabelingReservation(
                id=str(r.id),
                reservation_id=r.reservation_id,
                guest_name=r.guest_name,
                channel=ch.name if ch else None,
                checkin_date=r.checkin_date,
                checkout_date=r.checkout_date,
                nights=r.nights,
                gross_amount=float(r.gross_amount) if r.gross_amount is not None else None,
                net_amount=float(r.net_amount) if r.net_amount is not None else None,
                currency=r.currency,
            )
            for r, ch in reservations
        ],
    )


def _serialize(label: EvaluationLabel) -> LabelEntry:
    return LabelEntry(
        id=str(label.id),
        bank_transaction_id=str(label.bank_transaction_id),
        reservation_ids=[str(r) for r in (label.reservation_ids or [])],
        label_type=label.label_type,
        labeled_at=label.labeled_at.isoformat() if label.labeled_at else None,
    )


@router.get("/{reconciliation_id}/labels", response_model=list[LabelEntry])
def list_labels(
    reconciliation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = _ensure_owned(db, reconciliation_id, user)
    labels = (
        db.query(EvaluationLabel)
        .filter(EvaluationLabel.reconciliation_id == rec.id)
        .order_by(EvaluationLabel.labeled_at.asc())
        .all()
    )
    return [_serialize(l) for l in labels]


@router.post(
    "/{reconciliation_id}/labels",
    response_model=LabelEntry,
    status_code=status.HTTP_201_CREATED,
)
def create_or_replace_label(
    reconciliation_id: str,
    req: LabelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = _ensure_owned(db, reconciliation_id, user)
    if req.label_type not in ("match", "no_match"):
        raise HTTPException(status_code=422, detail="label_type must be 'match' or 'no_match'")
    if req.label_type == "match" and not req.reservation_ids:
        raise HTTPException(status_code=422, detail="match label needs reservation_ids")

    # Replace any existing label for this bank tx — one label per tx per session.
    db.query(EvaluationLabel).filter(
        EvaluationLabel.reconciliation_id == rec.id,
        EvaluationLabel.bank_transaction_id == uuid.UUID(req.bank_transaction_id),
    ).delete()

    label = EvaluationLabel(
        reconciliation_id=rec.id,
        bank_transaction_id=uuid.UUID(req.bank_transaction_id),
        reservation_ids=[uuid.UUID(r) for r in req.reservation_ids],
        label_type=req.label_type,
        labeled_by=user.id,
    )
    db.add(label)
    db.commit()
    db.refresh(label)
    return _serialize(label)


@router.delete("/{reconciliation_id}/labels/{bank_transaction_id}", status_code=204)
def delete_label(
    reconciliation_id: str,
    bank_transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = _ensure_owned(db, reconciliation_id, user)
    db.query(EvaluationLabel).filter(
        EvaluationLabel.reconciliation_id == rec.id,
        EvaluationLabel.bank_transaction_id == uuid.UUID(bank_transaction_id),
    ).delete()
    db.commit()
    return None


@router.get("/{reconciliation_id}/progress", response_model=LabelingProgress)
def progress(
    reconciliation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = _ensure_owned(db, reconciliation_id, user)
    total = (
        db.query(BankTransaction)
        .filter(BankTransaction.upload_id == rec.bank_upload_id)
        .count()
    )
    labels = (
        db.query(EvaluationLabel)
        .filter(EvaluationLabel.reconciliation_id == rec.id)
        .all()
    )
    return LabelingProgress(
        total_transactions=total,
        labeled_transactions=len(labels),
        matches=sum(1 for l in labels if l.label_type == "match"),
        no_matches=sum(1 for l in labels if l.label_type == "no_match"),
    )
