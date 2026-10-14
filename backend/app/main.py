from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.routers import (
    audit_logs,
    auth,
    dashboard,
    incidents,
    jobs,
    videos,
)
from app.websocket.routes import router as websocket_router

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    (Path(settings.UPLOAD_DIR) / "evidence").mkdir(parents=True, exist_ok=True)
    logger.info("SentinelAI backend starting up (env=%s)", settings.ENV)
    yield
    logger.info("SentinelAI backend shutting down")


app = FastAPI(
    title="SentinelAI: Edge Video Intelligence & Incident Detection Platform",
    description="API for video upload/analysis, incident detection, and dashboards.",
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
app.include_router(videos.router)
app.include_router(jobs.router)
app.include_router(incidents.router)
app.include_router(dashboard.router)
app.include_router(audit_logs.router)
app.include_router(websocket_router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}


@app.get("/", tags=["health"])
def root():
    return {"message": "SentinelAI API. See /docs for interactive API documentation."}
