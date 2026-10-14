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

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Uploads
    UPLOAD_DIR: str = "../uploads"
    MAX_UPLOAD_SIZE_MB: int = 500
    ALLOWED_VIDEO_EXTENSIONS: str = ".mp4,.avi,.mov,.mkv"

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
