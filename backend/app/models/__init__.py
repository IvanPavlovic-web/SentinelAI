"""Import all models so Base.metadata is fully populated for Alembic
autogenerate and for Base.metadata.create_all() in dev/seed scripts."""
from app.models.user import User, UserRole  # noqa: F401
from app.models.auth import RefreshToken, AuditLog  # noqa: F401
from app.models.camera import Camera, VideoSource, ProcessingJob, DetectionModel, JobStatus  # noqa: F401
from app.models.zone import Zone, Rule, ZoneSeverity  # noqa: F401
from app.models.tracking import TrackedObject, ObjectObservation  # noqa: F401
from app.models.incident import (  # noqa: F401
    Incident,
    IncidentEvidence,
    PerformanceMetric,
    IncidentStatus,
    IncidentPriority,
)
