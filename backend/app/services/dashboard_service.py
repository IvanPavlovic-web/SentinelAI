from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.camera import Camera, JobStatus, ProcessingJob, VideoSource
from app.models.incident import Incident, IncidentPriority, IncidentStatus, PerformanceMetric


def get_summary(db: Session) -> dict:
    # One query per table instead of one per metric (this used to be 13
    # round-trips: 2 for cameras, 1 for videos, 4 for job statuses, 2 for
    # incident counts, and 4 more -- one per IncidentPriority -- in a Python
    # loop). FILTER-qualified aggregates let Postgres compute every count
    # for a table in a single pass instead of rescanning it once per metric.
    total_cameras, active_cameras = db.query(
        func.count(Camera.id),
        func.count(Camera.id).filter(Camera.is_active.is_(True)),
    ).one()

    total_videos = db.query(func.count(VideoSource.id)).scalar()

    jobs_pending, jobs_processing, jobs_completed, jobs_failed = db.query(
        func.count(ProcessingJob.id).filter(ProcessingJob.status == JobStatus.PENDING),
        func.count(ProcessingJob.id).filter(ProcessingJob.status == JobStatus.PROCESSING),
        func.count(ProcessingJob.id).filter(ProcessingJob.status == JobStatus.COMPLETED),
        func.count(ProcessingJob.id).filter(ProcessingJob.status == JobStatus.FAILED),
    ).one()

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    open_incidents, incidents_last_24h = db.query(
        func.count(Incident.id).filter(Incident.status == IncidentStatus.OPEN),
        func.count(Incident.id).filter(Incident.detected_at >= since),
    ).one()

    incidents_by_priority = {p.value: 0 for p in IncidentPriority}
    for priority, count in db.query(Incident.priority, func.count(Incident.id)).group_by(Incident.priority).all():
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


def get_incident_analytics(db: Session, days: int = 14) -> dict:
    """Aggregated incident breakdowns for trend/heatmap-style views: when
    incidents happen (hour of day, daily trend), where (camera), and what
    (object class). Each breakdown is one grouped query -- real counts
    straight from the database, nothing computed by paging through rows in
    Python."""
    hour = func.extract("hour", Incident.detected_at).label("hour")
    by_hour = [
        {"hour": int(h), "count": count}
        for h, count in db.query(hour, func.count(Incident.id)).group_by(hour).order_by(hour).all()
    ]

    by_camera = [
        {
            "camera_id": camera_id,
            "camera_name": camera_name,
            "count": count,
            "avg_risk_score": round(avg_risk, 1) if avg_risk is not None else 0.0,
        }
        for camera_id, camera_name, count, avg_risk in (
            db.query(Incident.camera_id, Camera.name, func.count(Incident.id), func.avg(Incident.risk_score))
            .join(Camera, Incident.camera_id == Camera.id)
            .group_by(Incident.camera_id, Camera.name)
            .order_by(func.count(Incident.id).desc())
            .all()
        )
    ]

    by_object_class = [
        {"object_class": object_class, "count": count}
        for object_class, count in (
            db.query(Incident.object_class, func.count(Incident.id))
            .group_by(Incident.object_class)
            .order_by(func.count(Incident.id).desc())
            .all()
        )
    ]

    since = datetime.now(timezone.utc) - timedelta(days=days)
    day = func.date(Incident.detected_at).label("day")
    by_day = [
        {"date": d.isoformat() if hasattr(d, "isoformat") else str(d), "count": count}
        for d, count in (
            db.query(day, func.count(Incident.id))
            .filter(Incident.detected_at >= since)
            .group_by(day)
            .order_by(day)
            .all()
        )
    ]

    return {
        "by_hour": by_hour,
        "by_camera": by_camera,
        "by_object_class": by_object_class,
        "by_day": by_day,
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
