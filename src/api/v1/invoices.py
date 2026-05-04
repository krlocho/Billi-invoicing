import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import get_db
from src.models.invoice import Invoice
from src.models.user import User
from src.schemas.invoice import InvoiceGenerateRequest, InvoiceResponse

router = APIRouter()


def _generate_invoices_bg(tenant_id: str, reconciliation_id: str, match_ids: list[str] | None):
    from src.tasks.invoice_tasks import _generate_invoices_sync
    _generate_invoices_sync(tenant_id, reconciliation_id, match_ids)


@router.post("/generate", response_model=list[InvoiceResponse], status_code=201)
def generate_invoices(
    req: InvoiceGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    background_tasks.add_task(
        _generate_invoices_bg,
        str(user.tenant_id),
        req.reconciliation_id,
        req.match_ids,
    )
    return []  # Invoices generated async, poll via GET


@router.get("/", response_model=list[InvoiceResponse])
def list_invoices(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(Invoice)
        .filter(Invoice.tenant_id == user.tenant_id)
        .order_by(Invoice.created_at.desc())
        .all()
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    invoice = db.query(Invoice).filter(
        Invoice.id == uuid.UUID(invoice_id),
        Invoice.tenant_id == user.tenant_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    invoice = db.query(Invoice).filter(
        Invoice.id == uuid.UUID(invoice_id),
        Invoice.tenant_id == user.tenant_id,
    ).first()
    if not invoice or not invoice.pdf_path:
        raise HTTPException(status_code=404, detail="Invoice PDF not found")

    return FileResponse(
        invoice.pdf_path,
        media_type="application/pdf",
        filename=f"factura_{invoice.invoice_number}.pdf",
    )
