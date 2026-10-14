"""Application settings, loaded from environment variables / .env file."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "SentinelAI"
    ENV: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://sentinel:sentinel@localhost:5432/sentinel"

    # Auth / JWT
    JWT_SECRET: str = "CHANGE_ME_DEV_SECRET_DO_NOT_USE_IN_PROD"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_WORKER_CONCURRENCY: int = 4
    # Long-form camera footage can take hours to process; these are generous
    # ceilings, not tight limits. soft < hard so the task gets a chance to
    # flush partial progress/metrics before Celery kills it.
    CELERY_TASK_SOFT_TIME_LIMIT_SECONDS: int = 21600  # 6h
    CELERY_TASK_TIME_LIMIT_SECONDS: int = 23400  # 6.5h

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Uploads — sized for large enterprise camera/drone footage (multi-hour,
    # high-resolution recordings), not consumer clips. There is no hardcoded
    # ceiling in the code path itself (uploads stream to disk in 1MB chunks,
    # never buffered fully in memory); this is only a configurable safety
    # cap and can be raised arbitrarily, including disabled with 0.
    UPLOAD_DIR: str = "../uploads"
    MAX_UPLOAD_SIZE_MB: int = 0  # 0 = unlimited
    ALLOWED_VIDEO_EXTENSIONS: str = ".mp4,.avi,.mov,.mkv,.ts,.mxf,.webm"

    # Database connection pool — sized for many concurrent API/dashboard
    # clients and WebSocket connections typical of a multi-camera deployment.
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800

    # Pipeline defaults
    DEFAULT_CHUNK_SECONDS: int = 30
    FRAME_SAMPLE_RATE: int = 5  # sample every Nth frame
    YOLO_MODEL_PATH: str = "yolov8n.pt"
    INCIDENT_RISK_THRESHOLD: float = 70.0
    INCIDENT_CONSECUTIVE_REQUIRED: int = 3

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_video_extensions_list(self) -> list[str]:
        return [e.strip().lower() for e in self.ALLOWED_VIDEO_EXTENSIONS.split(",") if e.strip()]


settings = Settings()
