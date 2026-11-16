import logging

from celery import Celery
from celery.schedules import crontab

from .config import settings
from .processing import enforce_retention, job_lock, update_job, video_job
from .vision import MediaError, ModelError


logger = logging.getLogger(__name__)
cfg = settings()
worker = Celery("safevision", broker=cfg.redis_url)
worker.conf.update(
    task_ignore_result=True, task_acks_late=True, task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, task_soft_time_limit=840, task_time_limit=900,
    broker_transport_options={"visibility_timeout": 1800},
    broker_connection_retry_on_startup=True, task_serializer="json", accept_content=["json"],
    task_publish_retry=False, broker_connection_timeout=4,
    beat_schedule={"retention": {"task": "safevision.retention", "schedule": crontab(minute=15)}},
)


@worker.task(bind=True, max_retries=2, name="safevision.process")
def process(self, job_id):
    with job_lock(job_id) as acquired:
        if not acquired:
            return
        try:
            video_job(job_id)
        except (MediaError, ModelError) as exc:
            update_job(job_id, status="failed", error=str(exc))
        except Exception as exc:
            logger.exception("Falha no processamento do vídeo %s", job_id)
            if self.request.retries < self.max_retries:
                update_job(job_id, status="pending", progress=0, error="Nova tentativa programada.")
                raise self.retry(exc=exc, countdown=5 * (self.request.retries + 1))
            update_job(job_id, status="failed", error="Não foi possível processar o vídeo.")


@worker.task(name="safevision.retention")
def retention():
    enforce_retention()
