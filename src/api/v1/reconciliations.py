import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import get_db
from src.models.reconciliation import Reconciliation, ReconciliationMatch, MatchReservation
from src.models.feedback import ReconciliationFeedback
from src.models.user import User
from src.schemas.reconciliation import (
    MatchResponse,
    MatchUpdateRequest,
    ReconciliationCreate,
    ReconciliationResponse,
)

router = APIRouter()


@router.post("/", response_model=ReconciliationResponse, status_code=status.HTTP_201_CREATED)
def create_reconciliation(
    req: ReconciliationCreate,
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

    # Trigger async reconciliation
    from src.tasks.reconciliation_tasks import run_reconciliation
    run_reconciliation.delay(
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


@router.get("/{reconciliation_id}/matches", response_model=list[MatchResponse])
def list_matches(
    reconciliation_id: str,
    confidence_tier: str | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(ReconciliationMatch).filter(
        ReconciliationMatch.reconciliation_id == uuid.UUID(reconciliation_id)
    )
    if confidence_tier:
        query = query.filter(ReconciliationMatch.confidence_tier == confidence_tier.upper())
    if status_filter:
        query = query.filter(ReconciliationMatch.status == status_filter)

    matches = query.all()
    result = []
    for m in matches:
        res_ids = [str(mr.reservation_id) for mr in db.query(MatchReservation).filter(
            MatchReservation.match_id == m.id
        ).all()]
        result.append(MatchResponse(
            id=str(m.id),
            bank_transaction_id=str(m.bank_transaction_id),
            confidence_score=float(m.confidence_score) if m.confidence_score else None,
            confidence_tier=m.confidence_tier,
            amount_difference=float(m.amount_difference) if m.amount_difference else None,
            match_type=m.match_type,
            status=m.status,
            match_details=m.match_details,
            reservation_ids=res_ids,
        ))
    return result


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

    for match in matches:
        match.status = "confirmed"
        match.confirmed_by = user.id
        match.confirmed_at = datetime.now(timezone.utc)

    db.commit()
    return {"confirmed": len(matches)}
