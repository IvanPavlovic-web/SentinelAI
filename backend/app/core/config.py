"""Application settings, loaded from environment variables / .env file."""
from __future__ import annotations

from pydantic import model_validator
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

    # CORS. Includes http://localhost (port 80, i.e. no port in the Origin
    # header) because the frontend's API base URL is baked in at build time
    # as an absolute http://localhost:8000 (see docker-compose.yml
    # VITE_API_BASE_URL and frontend/src/api/client.ts), so even a page
    # served through the nginx entrypoint on :80 still calls the backend
    # directly on :8000 -- a cross-origin request from the browser's point
    # of view that needs this origin whitelisted, or every API call from
    # the nginx path fails outright with no access-control-allow-origin.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://localhost"

    # Uploads: sized for large enterprise camera/drone footage (multi-hour,
    # high-resolution recordings), not consumer clips. There is no hardcoded
    # ceiling in the code path itself (uploads stream to disk in 1MB chunks,
    # never buffered fully in memory); this is only a configurable safety
    # cap and can be raised arbitrarily, including disabled with 0.
    UPLOAD_DIR: str = "../uploads"
    MAX_UPLOAD_SIZE_MB: int = 0  # 0 = unlimited
    ALLOWED_VIDEO_EXTENSIONS: str = ".mp4,.avi,.mov,.mkv,.ts,.mxf,.webm"

    # Database connection pool: sized for many concurrent API/dashboard
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

    # Live camera monitoring (app/workers/tasks.py process_live_camera_task).
    # A single Celery task invocation runs for at most this long, then
    # re-queues itself if the camera is still active -- this keeps worker
    # slots healthy and lets Celery's own restart/retry machinery apply,
    # rather than one task looping forever.
    LIVE_SESSION_MAX_SECONDS: int = 300

    # Live activity-log generation (see app/workers/events.py). Detected
    # class names matching WEAPON_CLASS_NAMES (case-insensitive) are flagged
    # critical. The bundled yolov8n.pt is COCO-pretrained, and COCO's 80
    # classes do NOT include any weapon category (no gun/knife/rifle), so a
    # second, dedicated weapon-detection model runs alongside it on every
    # sampled frame (see app/workers/detection.py load_weapon_model /
    # detect_weapons) and is normalized into these class names. Disable with
    # WEAPON_MODEL_ENABLED=false (e.g. fully offline environments); detection
    # then degrades gracefully to COCO classes only.
    WEAPON_CLASS_NAMES: str = "knife,gun,pistol,rifle,weapon,firearm,grenade,missile"

    # Dedicated weapon-detection model (separate from YOLO_MODEL_PATH above,
    # which is COCO-only). Downloaded once from the Hugging Face Hub (a
    # model repo by default, or a Space repo -- WEAPON_MODEL_REPO_TYPE --
    # since several community weapon-detection checkpoints are only
    # published inside a Space) and cached locally via huggingface_hub; any
    # failure to fetch or load it (no internet, gated repo, package
    # missing) disables weapon detection for that session only -- the rest
    # of the pipeline keeps running, same fallback philosophy as the stub
    # detector. The default (Dricz/Weapon_Detection_YOLOv8-4) is a 5-class
    # YOLOv8 checkpoint covering grenade/knife/missile/pistol/rifle, so
    # knives are covered out of the box. It does NOT cover batons/sticks --
    # no pretrained open-source checkpoint for that exists as of this
    # writing (see README "Known limitations"); point
    # WEAPON_MODEL_REPO_ID/WEAPON_MODEL_FILENAME at a different model to
    # extend or replace coverage, no code changes needed.
    WEAPON_MODEL_ENABLED: bool = True
    WEAPON_MODEL_REPO_ID: str = "Dricz/Weapon_Detection_YOLOv8-4"
    WEAPON_MODEL_FILENAME: str = "50epoch-new-weapon.pt"
    WEAPON_MODEL_REPO_TYPE: str = "space"
    WEAPON_MODEL_CONFIDENCE: float = 0.45
    # Class name used when the weapon model's own label isn't already one
    # of WEAPON_CLASS_NAMES.
    WEAPON_MODEL_FALLBACK_CLASS: str = "weapon"
    ANOMALY_EVENT_THRESHOLD: float = 0.5  # motion_anomaly score that counts as "suspicious movement"
    EVENT_HEARTBEAT_SECONDS: float = 3.0  # max gap before a routine "still visible" status line

    # Weapon<->person association (app/workers/tracking_pipeline.py
    # associate_weapons_to_people): a weapon-class detection within this
    # fraction of the frame diagonal of a person track's last centroid is
    # treated as "held by" that person, producing a specific narration
    # ("Person #3 appears to be holding a knife") and immediately creating
    # a CRITICAL incident, independent of any zone/rule configuration --
    # a weapon next to a person is inherently an incident worth surfacing.
    WEAPON_PERSON_ASSOCIATION_MAX_DISTANCE_RATIO: float = 0.25

    # --- Real-time alerting (app/services/alert_service.py) ---
    # Delivers incidents at or above ALERT_MIN_PRIORITY to email and/or a
    # generic webhook (Slack/Discord/PagerDuty/etc. all accept a plain JSON
    # POST). Both channels are optional and independently configured; if
    # neither is set, alerting is a no-op. ALERT_COOLDOWN_SECONDS suppresses
    # repeat alerts for the same camera+object_class so one lingering
    # detection doesn't page someone every few seconds.
    ALERT_ENABLED: bool = True
    ALERT_MIN_PRIORITY: str = "high"  # low|medium|high|critical
    ALERT_COOLDOWN_SECONDS: float = 120.0
    ALERT_SMTP_HOST: str = ""
    ALERT_SMTP_PORT: int = 587
    ALERT_SMTP_USE_TLS: bool = True
    ALERT_SMTP_USER: str = ""
    ALERT_SMTP_PASSWORD: str = ""
    ALERT_EMAIL_FROM: str = "alerts@sentinelai.local"
    ALERT_EMAIL_TO: str = ""
    ALERT_WEBHOOK_URL: str = ""

    # --- Auth rate limiting (app/core/rate_limit.py) ---
    # Redis-backed (correct across multiple uvicorn worker processes),
    # fixed-window, per-client-IP. Protects /api/auth/login and /register
    # against brute-force/credential-stuffing and registration spam.
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT_MAX: int = 10
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 60
    REGISTER_RATE_LIMIT_MAX: int = 5
    REGISTER_RATE_LIMIT_WINDOW_SECONDS: int = 3600

    @model_validator(mode="after")
    def _validate_production_safety(self) -> "Settings":
        """Fails fast at startup, rather than quietly running insecurely,
        when ENV=production still has dev-only defaults in place. This is
        deliberately a hard error (not a warning) for the secret itself,
        since a wrong-but-running deployment is worse than one that
        refuses to start."""
        if self.ENV.lower() == "production":
            if self.JWT_SECRET == "CHANGE_ME_DEV_SECRET_DO_NOT_USE_IN_PROD" or len(self.JWT_SECRET) < 32:
                raise ValueError(
                    "JWT_SECRET must be set to a long random value in production "
                    "(ENV=production with the default/short secret refuses to start)."
                )
            if self.DEBUG:
                raise ValueError("DEBUG must be false when ENV=production.")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_video_extensions_list(self) -> list[str]:
        return [e.strip().lower() for e in self.ALLOWED_VIDEO_EXTENSIONS.split(",") if e.strip()]

    @property
    def weapon_class_names_set(self) -> set[str]:
        return {c.strip().lower() for c in self.WEAPON_CLASS_NAMES.split(",") if c.strip()}


settings = Settings()
