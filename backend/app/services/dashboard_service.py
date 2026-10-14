from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.camera import Camera, JobStatus, ProcessingJob, VideoSource
from app.models.incident import Incident, IncidentPriority, IncidentStatus, PerformanceMetric


def get_summary(db: Session) -> dict:
    total_cameras = db.query(Camera).count()
    active_cameras = db.query(Camera).filter(Camera.is_active.is_(True)).count()
    total_videos = db.query(VideoSource).count()

    jobs_pending = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.PENDING).count()
    jobs_processing = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.PROCESSING).count()
    jobs_completed = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.COMPLETED).count()
    jobs_failed = db.query(ProcessingJob).filter(ProcessingJob.status == JobStatus.FAILED).count()

    open_incidents = db.query(Incident).filter(Incident.status == IncidentStatus.OPEN).count()

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    incidents_last_24h = db.query(Incident).filter(Incident.detected_at >= since).count()

    incidents_by_priority = {}
    for priority in IncidentPriority:
        count = db.query(Incident).filter(Incident.priority == priority).count()
        incidents_by_priority[priority.value] = count

    return {
        "total_cameras": total_cameras,
        "active_cameras": active_cameras,
        "total_videos": total_videos,
        "jobs_pending": jobs_pending,
        "jobs_processing": jobs_processing,
        "jobs_completed": jobs_completed,
        "jobs_failed": jobs_failed,
        "open_incidents": open_incidents,
        "incidents_last_24h": incidents_last_24h,
        "incidents_by_priority": incidents_by_priority,
    }


def get_performance(db: Session, limit: int = 50) -> list[dict]:
    rows = (
        db.query(PerformanceMetric)
        .order_by(PerformanceMetric.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "job_id": r.processing_job_id,
            "created_at": r.created_at.isoformat(),
            "processing_fps": r.processing_fps,
            "avg_latency_ms": r.avg_latency_ms,
            "p95_latency_ms": r.p95_latency_ms,
            "avg_cpu_percent": r.avg_cpu_percent,
            "avg_ram_mb": r.avg_ram_mb,
            "incident_count": r.incident_count,
        }
        for r in reversed(rows)
    ]
