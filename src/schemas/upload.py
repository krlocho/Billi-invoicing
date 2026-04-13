from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class UploadResponse(BaseModel):
    id: UUID
    file_type: str
    original_filename: str | None
    status: str
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BankTransactionResponse(BaseModel):
    id: UUID
    transaction_date: str
    description: str
    amount: float
    balance: float | None
    is_reconciled: bool

    model_config = {"from_attributes": True}


class ChannelReservationResponse(BaseModel):
    id: UUID
    reservation_id: str | None
    guest_name: str | None
    checkin_date: str | None
    checkout_date: str | None
    room_type: str | None
    nights: int | None
    gross_amount: float | None
    net_amount: float | None
    status: str | None
    is_reconciled: bool

    model_config = {"from_attributes": True}
