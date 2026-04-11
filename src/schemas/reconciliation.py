from datetime import datetime
from pydantic import BaseModel


class ReconciliationCreate(BaseModel):
    bank_upload_id: str
    channel_upload_ids: list[str]


class ReconciliationResponse(BaseModel):
    id: str
    status: str
    total_transactions: int | None
    matched_auto: int
    matched_manual: int
    unmatched: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchResponse(BaseModel):
    id: str
    bank_transaction_id: str
    confidence_score: float | None
    confidence_tier: str | None
    amount_difference: float | None
    match_type: str | None
    status: str
    match_details: dict | None
    reservation_ids: list[str] = []

    model_config = {"from_attributes": True}


class MatchUpdateRequest(BaseModel):
    status: str  # confirmed, rejected
    reservation_ids: list[str] | None = None  # for reassignment
