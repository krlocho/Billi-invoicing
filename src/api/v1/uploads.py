import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import get_db
from src.models.upload import Upload
from src.models.user import User
from src.schemas.upload import UploadResponse
from src.utils.storage import save_upload

router = APIRouter()


def _process_bank_upload(upload_id: str):
    """Process bank statement synchronously."""
    from src.tasks.ocr_tasks import _process_bank_statement_sync
    _process_bank_statement_sync(upload_id)


def _process_channel_upload(upload_id: str):
    """Process channel file synchronously."""
    from src.tasks.ocr_tasks import _process_channel_file_sync
    _process_channel_file_sync(upload_id)


@router.post("/bank-statement", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_bank_statement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted for bank statements")

    content = await file.read()
    stored_path = save_upload(content, file.filename, "bank_statements")

    upload = Upload(
        tenant_id=user.tenant_id,
        file_type="bank_statement",
        original_filename=file.filename,
        stored_path=stored_path,
        status="pending",
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    background_tasks.add_task(_process_bank_upload, str(upload.id))
    return upload


@router.post("/channel-file", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_channel_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    channel_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only CSV/Excel files are accepted")

    content = await file.read()
    stored_path = save_upload(content, file.filename, "channel_files")

    upload = Upload(
        tenant_id=user.tenant_id,
        file_type="channel_file",
        channel_id=uuid.UUID(channel_id),
        original_filename=file.filename,
        stored_path=stored_path,
        status="pending",
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    background_tasks.add_task(_process_channel_upload, str(upload.id))
    return upload


@router.get("/{upload_id}", response_model=UploadResponse)
def get_upload(upload_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    upload = db.query(Upload).filter(
        Upload.id == uuid.UUID(upload_id), Upload.tenant_id == user.tenant_id
    ).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload


@router.get("/", response_model=list[UploadResponse])
def list_uploads(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Upload).filter(Upload.tenant_id == user.tenant_id).order_by(Upload.created_at.desc()).all()
