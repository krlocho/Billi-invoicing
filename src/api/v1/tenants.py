from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import get_db
from src.models.tenant import Tenant
from src.models.user import User
from src.schemas.tenant import TenantResponse, TenantSettings, TenantUpdate

router = APIRouter()

DEFAULT_SETTINGS = TenantSettings()


def _serialize(tenant: Tenant) -> TenantResponse:
    raw = tenant.settings or {}
    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        tax_id=tenant.tax_id,
        address=tenant.address,
        settings=TenantSettings(
            tax_type=raw.get("tax_type", DEFAULT_SETTINGS.tax_type),
            tax_rate=float(raw.get("tax_rate", DEFAULT_SETTINGS.tax_rate)),
            country=raw.get("country"),
            region=raw.get("region"),
        ),
    )


@router.get("/me", response_model=TenantResponse)
def get_my_tenant(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _serialize(tenant)


@router.put("/me", response_model=TenantResponse)
def update_my_tenant(
    req: TenantUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if req.name is not None:
        tenant.name = req.name
    if req.tax_id is not None:
        tenant.tax_id = req.tax_id
    if req.address is not None:
        tenant.address = req.address
    if req.settings is not None:
        merged = dict(tenant.settings or {})
        merged.update(req.settings.model_dump(exclude_none=True))
        tenant.settings = merged

    db.commit()
    db.refresh(tenant)
    return _serialize(tenant)
