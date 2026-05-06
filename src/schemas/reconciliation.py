from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel


class ReconciliationCreate(BaseModel):
    bank_upload_id: str
    channel_upload_ids: list[str]


class ReconciliationResponse(BaseModel):
    id: UUID
    status: str
    total_transactions: int | None
    matched_auto: int
    matched_manual: int
    unmatched: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BankTransactionInfo(BaseModel):
    id: UUID
    transaction_date: date
    description: str
    amount: float
    detected_channel: str | None = None


class ReservationInfo(BaseModel):
    id: UUID
    guest_name: str | None
    channel: str | None
    checkin_date: date | None
    checkout_date: date | None
    nights: int | None
    gross_amount: float | None
    net_amount: float | None
    currency: str | None


class MatchResponse(BaseModel):
    id: UUID
    bank_transaction_id: UUID
    confidence_score: float | None
    confidence_tier: str | None
    amount_difference: float | None
    match_type: str | None
    status: str
    match_details: dict | None
    reservation_ids: list[str] = []
    bank_transaction: BankTransactionInfo | None = None
    reservations: list[ReservationInfo] = []

    model_config = {"from_attributes": True}


class UnmatchedTransactionResponse(BaseModel):
    id: UUID
    transaction_date: date
    description: str
    amount: float
    detected_channel: str | None = None


class MatchUpdateRequest(BaseModel):
    status: str  # confirmed, rejected
    reservation_ids: list[str] | None = None  # for reassignment
