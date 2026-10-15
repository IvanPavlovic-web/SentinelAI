from __future__ import annotations

import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.routers import (
    alerts,
    audit_logs,
    auth,
    cameras,
    dashboard,
    incidents,
    jobs,
    rules,
    videos,
    zones,
)
from app.websocket.routes import router as websocket_router

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    (Path(settings.UPLOAD_DIR) / "evidence").mkdir(parents=True, exist_ok=True)
    (Path(settings.UPLOAD_DIR) / "live").mkdir(parents=True, exist_ok=True)
    logger.info("SentinelAI backend starting up (env=%s)", settings.ENV)
    yield
    logger.info("SentinelAI backend shutting down")


app = FastAPI(
    title="SentinelAI: Edge Video Intelligence & Incident Detection Platform",
    description="API for live camera monitoring, video upload/analysis, incident detection, and dashboards.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(videos.router)
app.include_router(jobs.router)
app.include_router(incidents.router)
app.include_router(dashboard.router)
app.include_router(audit_logs.router)
app.include_router(alerts.router)
app.include_router(zones.router)
app.include_router(rules.router)
app.include_router(websocket_router)


def _sanitize_for_json(value: Any) -> Any:
    """Recursively makes a Pydantic/FastAPI validation-error payload safe
    to pass to Starlette's JSONResponse (which calls json.dumps with the
    strict, spec-compliant allow_nan=False). Two distinct ways this
    otherwise breaks, both confirmed live:
    1. Non-finite floats (NaN/Infinity/-Infinity): Pydantic happily parses
       these as valid floats and echoes the original input back in the
       error's "input" field, which then fails to serialize.
    2. A @field_validator that raises ValueError (e.g. the zone polygon's
       range check): Pydantic v2 wraps it as ctx.error holding the actual
       exception *object*, not its message -- plain json.dumps has no
       idea how to encode an exception instance at all.
    Without this, both cases turned what should be a clean 422 into an
    unhandled 500 (only ever caught by the generic Exception handler
    below) -- on a field a request had *already failed to validate*."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)  # anything else json.dumps can't natively encode (e.g. ctx.error's exception object)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": _sanitize_for_json(exc.errors())})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catches anything that escapes a route handler. In production this
    must never leak a stack trace or internal exception message to the
    client (information disclosure); it's always logged in full
    server-side, where an operator can actually act on it."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    detail = str(exc) if settings.DEBUG else "Internal server error"
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": detail})


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}


@app.get("/", tags=["health"])
def root():
    return {"message": "SentinelAI API. See /docs for interactive API documentation."}
