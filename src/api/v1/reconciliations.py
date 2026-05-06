import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import get_db
from src.models.bank_transaction import BankTransaction
from src.models.channel import Channel
from src.models.channel_reservation import ChannelReservation
from src.models.reconciliation import Reconciliation, ReconciliationMatch, MatchReservation
from src.models.feedback import ReconciliationFeedback
from src.models.user import User
from src.schemas.reconciliation import (
    BankTransactionInfo,
    MatchResponse,
    MatchUpdateRequest,
    ReconciliationCreate,
    ReconciliationResponse,
    ReservationInfo,
    UnmatchedTransactionResponse,
)

router = APIRouter()


def _run_reconciliation_task(reconciliation_id: str, bank_upload_id: str, channel_upload_ids: list[str]):
    """Run reconciliation synchronously."""
    from src.tasks.reconciliation_tasks import _run_reconciliation_sync
    _run_reconciliation_sync(reconciliation_id, bank_upload_id, channel_upload_ids)


@router.post("/", response_model=ReconciliationResponse, status_code=status.HTTP_201_CREATED)
def create_reconciliation(
    req: ReconciliationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    reconciliation = Reconciliation(
        tenant_id=user.tenant_id,
        bank_upload_id=uuid.UUID(req.bank_upload_id),
        status="pending",
    )
    db.add(reconciliation)
    db.commit()
    db.refresh(reconciliation)

    background_tasks.add_task(
        _run_reconciliation_task,
        str(reconciliation.id),
        req.bank_upload_id,
        req.channel_upload_ids,
    )

    return reconciliation


@router.get("/{reconciliation_id}", response_model=ReconciliationResponse)
def get_reconciliation(
    reconciliation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = db.query(Reconciliation).filter(
        Reconciliation.id == uuid.UUID(reconciliation_id),
        Reconciliation.tenant_id == user.tenant_id,
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    return rec


def _build_match_response(
    db: Session, m: ReconciliationMatch
) -> MatchResponse:
    bank_tx = db.query(BankTransaction).filter(BankTransaction.id == m.bank_transaction_id).first()
    bank_tx_info = None
    if bank_tx:
        detected_channel = None
        if bank_tx.detected_channel_id:
            ch = db.query(Channel).filter(Channel.id == bank_tx.detected_channel_id).first()
            if ch:
                detected_channel = ch.name
        bank_tx_info = BankTransactionInfo(
            id=bank_tx.id,
            transaction_date=bank_tx.transaction_date,
            description=bank_tx.description,
            amount=float(bank_tx.amount),
            detected_channel=detected_channel,
        )

    reservations: list[ReservationInfo] = []
    res_rows = (
        db.query(ChannelReservation, Channel)
        .outerjoin(Channel, ChannelReservation.channel_id == Channel.id)
        .join(MatchReservation, MatchReservation.reservation_id == ChannelReservation.id)
        .filter(MatchReservation.match_id == m.id)
        .order_by(ChannelReservation.checkout_date.asc().nullslast())
        .all()
    )
    for r, ch in res_rows:
        reservations.append(ReservationInfo(
            id=r.id,
            guest_name=r.guest_name,
            channel=ch.name if ch else None,
            checkin_date=r.checkin_date,
            checkout_date=r.checkout_date,
            nights=r.nights,
            gross_amount=float(r.gross_amount) if r.gross_amount is not None else None,
            net_amount=float(r.net_amount) if r.net_amount is not None else None,
            currency=r.currency,
        ))

    return MatchResponse(
        id=m.id,
        bank_transaction_id=m.bank_transaction_id,
        confidence_score=float(m.confidence_score) if m.confidence_score is not None else None,
        confidence_tier=m.confidence_tier,
        amount_difference=float(m.amount_difference) if m.amount_difference is not None else None,
        match_type=m.match_type,
        status=m.status,
        match_details=m.match_details,
        reservation_ids=[str(r.id) for r in reservations],
        bank_transaction=bank_tx_info,
        reservations=reservations,
    )


@router.get("/{reconciliation_id}/matches", response_model=list[MatchResponse])
def list_matches(
    reconciliation_id: str,
    confidence_tier: str | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        db.query(ReconciliationMatch)
        .join(BankTransaction, ReconciliationMatch.bank_transaction_id == BankTransaction.id)
        .filter(ReconciliationMatch.reconciliation_id == uuid.UUID(reconciliation_id))
        .order_by(BankTransaction.transaction_date.asc())
    )
    if confidence_tier:
        query = query.filter(ReconciliationMatch.confidence_tier == confidence_tier.upper())
    if status_filter:
        query = query.filter(ReconciliationMatch.status == status_filter)

    matches = query.all()
    return [_build_match_response(db, m) for m in matches]


@router.get(
    "/{reconciliation_id}/unmatched-transactions",
    response_model=list[UnmatchedTransactionResponse],
)
def list_unmatched_transactions(
    reconciliation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = db.query(Reconciliation).filter(
        Reconciliation.id == uuid.UUID(reconciliation_id),
        Reconciliation.tenant_id == user.tenant_id,
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    matched_tx_ids = {
        m.bank_transaction_id
        for m in db.query(ReconciliationMatch.bank_transaction_id)
        .filter(ReconciliationMatch.reconciliation_id == rec.id)
        .all()
    }
    txs = (
        db.query(BankTransaction)
        .filter(BankTransaction.upload_id == rec.bank_upload_id)
        .order_by(BankTransaction.transaction_date.asc())
        .all()
    )
    unmatched = [t for t in txs if t.id not in matched_tx_ids]
    out: list[UnmatchedTransactionResponse] = []
    for t in unmatched:
        ch_name = None
        if t.detected_channel_id:
            ch = db.query(Channel).filter(Channel.id == t.detected_channel_id).first()
            if ch:
                ch_name = ch.name
        out.append(UnmatchedTransactionResponse(
            id=t.id,
            transaction_date=t.transaction_date,
            description=t.description,
            amount=float(t.amount),
            detected_channel=ch_name,
        ))
    return out


@router.put("/{reconciliation_id}/matches/{match_id}", response_model=MatchResponse)
def update_match(
    reconciliation_id: str,
    match_id: str,
    req: MatchUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    match = db.query(ReconciliationMatch).filter(
        ReconciliationMatch.id == uuid.UUID(match_id),
        ReconciliationMatch.reconciliation_id == uuid.UUID(reconciliation_id),
    ).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Save feedback for learning
    previous_state = {"status": match.status, "confidence_tier": match.confidence_tier}

    match.status = req.status
    if req.status == "confirmed":
        match.confirmed_by = user.id
        from datetime import datetime, timezone
        match.confirmed_at = datetime.now(timezone.utc)

    # Handle reassignment
    if req.reservation_ids is not None:
        db.query(MatchReservation).filter(MatchReservation.match_id == match.id).delete()
        for rid in req.reservation_ids:
            db.add(MatchReservation(match_id=match.id, reservation_id=uuid.UUID(rid)))

    feedback = ReconciliationFeedback(
        match_id=match.id,
        action=req.status,
        previous_state=previous_state,
        new_state={"status": req.status},
        user_id=user.id,
    )
    db.add(feedback)
    db.commit()

    # Re-learn commission rates affected by this confirmation. Touches the
    # channels of every reservation linked to this match.
    if req.status == "confirmed":
        from src.matching.learned_commission import update_channel_learned_commission
        affected_channels = {
            cr.channel_id
            for cr in db.query(ChannelReservation)
            .join(MatchReservation, MatchReservation.reservation_id == ChannelReservation.id)
            .filter(MatchReservation.match_id == match.id)
            .all()
        }
        for ch_id in affected_channels:
            update_channel_learned_commission(db, user.tenant_id, ch_id)
        db.commit()

    db.refresh(match)

    res_ids = [str(mr.reservation_id) for mr in db.query(MatchReservation).filter(
        MatchReservation.match_id == match.id
    ).all()]

    return MatchResponse(
        id=str(match.id),
        bank_transaction_id=str(match.bank_transaction_id),
        confidence_score=float(match.confidence_score) if match.confidence_score else None,
        confidence_tier=match.confidence_tier,
        amount_difference=float(match.amount_difference) if match.amount_difference else None,
        match_type=match.match_type,
        status=match.status,
        match_details=match.match_details,
        reservation_ids=res_ids,
    )


@router.post("/{reconciliation_id}/confirm-all")
def confirm_all_high_confidence(
    reconciliation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone

    matches = db.query(ReconciliationMatch).filter(
        ReconciliationMatch.reconciliation_id == uuid.UUID(reconciliation_id),
        ReconciliationMatch.confidence_tier == "HIGH",
        ReconciliationMatch.status == "pending",
    ).all()

    affected_channels: set = set()
    for match in matches:
        match.status = "confirmed"
        match.confirmed_by = user.id
        match.confirmed_at = datetime.now(timezone.utc)
        affected_channels.update(
            cr.channel_id
            for cr in db.query(ChannelReservation)
            .join(MatchReservation, MatchReservation.reservation_id == ChannelReservation.id)
            .filter(MatchReservation.match_id == match.id)
            .all()
        )
    db.commit()

    if affected_channels:
        from src.matching.learned_commission import update_channel_learned_commission
        for ch_id in affected_channels:
            update_channel_learned_commission(db, user.tenant_id, ch_id)
        db.commit()

    return {"confirmed": len(matches)}
