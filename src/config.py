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
    default_llm_provider: str = "anthropic"  # "anthropic" or "openai"
    default_llm_model: str = "claude-sonnet-4-20250514"

    # Invoice
    default_tax_rate: float = 10.0  # IVA for hotels in Spain

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
