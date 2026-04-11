from fastapi import APIRouter

from src.api.v1 import auth, uploads, reconciliations, invoices

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(uploads.router, prefix="/uploads", tags=["Uploads"])
router.include_router(reconciliations.router, prefix="/reconciliations", tags=["Reconciliations"])
router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
