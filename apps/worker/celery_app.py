from celery import Celery
from apps.api.app.redis_config import get_redis_url

broker = get_redis_url(default_db=1)

celery_app = Celery(
    "datumor",
    broker=broker,
    backend=broker,
    include=["apps.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 86400},
    result_backend_transport_options={"visibility_timeout": 86400},
    visibility_timeout=86400,
)
