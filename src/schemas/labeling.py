from datetime import date
from pydantic import BaseModel


class LabelingTransaction(BaseModel):
    id: str
    transaction_date: date
    description: str
    amount: float


class LabelingReservation(BaseModel):
    id: str
    reservation_id: str | None
    guest_name: str | None
    channel: str | None
    checkin_date: date | None
    checkout_date: date | None
    nights: int | None
    gross_amount: float | None
    net_amount: float | None
    currency: str
    room_type: str | None = None


class LabelingDataset(BaseModel):
    reconciliation_id: str
    transactions: list[LabelingTransaction]
    reservations: list[LabelingReservation]


class LabelEntry(BaseModel):
    id: str
    bank_transaction_id: str
    reservation_ids: list[str]
    label_type: str
    labeled_at: str | None = None


class LabelCreate(BaseModel):
    bank_transaction_id: str
    reservation_ids: list[str] = []
    label_type: str  # "match" or "no_match"


class LabelingProgress(BaseModel):
    total_transactions: int
    labeled_transactions: int
    matches: int
    no_matches: int
