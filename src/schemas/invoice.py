from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel


class InvoiceGenerateRequest(BaseModel):
    reconciliation_id: str
    match_ids: list[str] | None = None  # if None, generate for all confirmed matches


class InvoiceResponse(BaseModel):
    id: UUID
    invoice_number: str
    guest_name: str | None
    issue_date: date
    checkin_date: date | None
    checkout_date: date | None
    subtotal: float | None
    tax_rate: float | None
    tax_amount: float | None
    total: float | None
    currency: str
    status: str
    pdf_path: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
