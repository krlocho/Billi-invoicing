from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "Billi Invoicing"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql://billi:billi@localhost:5432/billi"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    # File storage
    upload_dir: str = "./uploads"

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    default_llm_provider: str = "google"  # "anthropic", "openai", or "google"
    default_llm_model: str = "gemini-2.5-flash"

    # Invoice — tax is configurable per tenant, NOT hardcoded
    # IGIC 7% (Canarias), IVA 10% (Spain mainland), VAT varies (EU)
    # This default is only used when no tenant config exists
    default_tax_rate: float = 10.0
    default_tax_type: str = "IVA"  # IVA, IGIC, VAT, TVA, MwSt, etc.

    model_config = {"env_file": [".env.local", ".env"], "env_file_encoding": "utf-8"}


settings = Settings()
