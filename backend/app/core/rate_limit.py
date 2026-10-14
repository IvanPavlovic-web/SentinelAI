"""Redis-backed fixed-window rate limiter for auth endpoints, to slow down
credential-stuffing / brute-force attempts. Backed by Redis (not an
in-memory counter) so the limit is correct across multiple uvicorn worker
processes (UVICORN_WORKERS), which don't share memory.

Fails open: if Redis itself is unreachable, requests are allowed through
rather than locking every user out because of an unrelated outage.
"""
from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis

logger = get_logger(__name__)


def rate_limit(key_prefix: str, max_requests: int, window_seconds: int):
    """Returns a FastAPI dependency enforcing `max_requests` per
    `window_seconds` per client IP, namespaced by `key_prefix` so different
    endpoints don't share a counter."""

    def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{key_prefix}:{client_ip}"
        try:
            client = get_redis()
            count = client.incr(key)
            if count == 1:
                client.expire(key, window_seconds)
            if count > max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please wait and try again.",
                )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - Redis unavailable: fail open
            logger.warning("Rate limiter unavailable (%s); allowing request through.", exc)

    return dependency
