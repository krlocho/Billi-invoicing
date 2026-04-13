from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from src.api.v1 import router as api_v1_router
from src.config import settings

app = FastAPI(
    title=settings.app_name,
    description="AI-powered invoice reconciliation system for hotels",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}
