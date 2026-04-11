from celery import Celery

from src.config import settings

celery = Celery(
    "billi",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Madrid",
    enable_utc=True,
    task_track_started=True,
)

celery.autodiscover_tasks(["src.tasks"])
