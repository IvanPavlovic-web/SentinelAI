"""Shared synchronous Redis client. Used for cross-process state that a
single-process in-memory dict can't safely hold: the login rate limiter
(app/core/rate_limit.py, must be consistent across multiple uvicorn
workers) and live-camera tracker-state persistence across re-queued
Celery task invocations (app/workers/tracking_pipeline.py).

A lazily-created module-level singleton, same pattern as a DB connection
pool: one client per process, reused across requests/tasks instead of
reconnecting every call.
"""
from __future__ import annotations

import redis

from app.core.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _client
