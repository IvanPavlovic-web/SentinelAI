from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "sentinelai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    # Enterprise-scale footage (multi-hour, high-resolution) needs generous
    # time limits rather than Celery's short defaults; soft fires first so
    # the task can still persist partial progress/metrics before the hard
    # limit kills the worker process.
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT_SECONDS,
    # Ack after completion (not on delivery) so a crashed/killed worker
    # re-queues the job instead of silently losing a long-running video job.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=604800,  # 7 days, long enough for an ops team to review job history
)
