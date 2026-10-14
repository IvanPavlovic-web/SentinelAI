from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.camera import ProcessingJob
from app.models.incident import PerformanceMetric
from app.models.tracking import ActivityEvent, ObjectObservation, TrackedObject


def get_job(db: Session, job_id: int) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found")
    return job


def get_job_metrics(db: Session, job_id: int) -> list[PerformanceMetric]:
    get_job(db, job_id)  # validate exists
    return (
        db.query(PerformanceMetric)
        .filter(PerformanceMetric.processing_job_id == job_id)
        .order_by(PerformanceMetric.created_at.desc())
        .all()
    )


def get_job_detection_counts(db: Session, job_id: int) -> dict:
    """Lightweight live summary: one cheap group-by query, safe to call on
    every WebSocket poll tick (every ~1s) while a job is still processing,
    since tracked_objects/object_observations rows are committed
    incrementally as the pipeline runs, not only at the end."""
    rows = (
        db.query(TrackedObject.object_class, func.count(TrackedObject.id))
        .filter(TrackedObject.processing_job_id == job_id)
        .group_by(TrackedObject.object_class)
        .all()
    )
    class_counts = {object_class: count for object_class, count in rows}
    return {
        "class_counts": class_counts,
        "total_tracked_objects": sum(class_counts.values()),
    }


def get_job_events(db: Session, job_id: int, limit: int = 500) -> list[dict]:
    """The full live-activity narration log for a job, oldest first: what
    GET /api/jobs/{id}/events returns for post-hoc review of a completed
    job. The WebSocket carries only the newest slice of this while a job
    is still processing (see get_recent_events)."""
    get_job(db, job_id)  # validate exists
    rows = (
        db.query(ActivityEvent)
        .filter(ActivityEvent.processing_job_id == job_id)
        .order_by(ActivityEvent.timestamp_seconds.asc(), ActivityEvent.id.asc())
        .limit(limit)
        .all()
    )
    return [_serialize_event(e) for e in rows]


def get_recent_events(db: Session, job_id: int, limit: int = 15) -> list[dict]:
    """Newest `limit` events, oldest-first within that slice, cheap enough
    to call on every WebSocket poll tick while a job is processing."""
    rows = (
        db.query(ActivityEvent)
        .filter(ActivityEvent.processing_job_id == job_id)
        .order_by(ActivityEvent.id.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_event(e) for e in reversed(rows)]


def _serialize_event(e: ActivityEvent) -> dict:
    return {
        "id": e.id,
        "track_number": e.track_number,
        "object_class": e.object_class,
        "timestamp_seconds": e.timestamp_seconds,
        "event_type": e.event_type,
        "severity": e.severity.value,
        "description": e.description,
        "risk_score": e.risk_score,
    }


def get_job_detections(db: Session, job_id: int) -> dict:
    """Full per-track detection detail for a job: what was detected, how
    often, how confidently, and its final Risk score, independent of
    whether the video's camera has any zones/rules configured, so 'what is
    in this footage' is always answerable, not just 'did it trigger an
    incident'."""
    get_job(db, job_id)  # validate exists

    counts = get_job_detection_counts(db, job_id)

    tracks = (
        db.query(TrackedObject)
        .filter(TrackedObject.processing_job_id == job_id)
        .order_by(TrackedObject.first_seen_at.asc())
        .all()
    )

    agg_rows = (
        db.query(
            ObjectObservation.tracked_object_id,
            func.max(ObjectObservation.confidence).label("max_confidence"),
            func.count(ObjectObservation.id).label("observation_count"),
        )
        .join(TrackedObject, ObjectObservation.tracked_object_id == TrackedObject.id)
        .filter(TrackedObject.processing_job_id == job_id)
        .group_by(ObjectObservation.tracked_object_id)
        .all()
    )
    agg_by_track = {row.tracked_object_id: row for row in agg_rows}

    track_rows = []
    for t in tracks:
        agg = agg_by_track.get(t.id)
        track_rows.append(
            {
                "track_number": t.track_number,
                "object_class": t.object_class,
                "first_seen_at": t.first_seen_at.isoformat(),
                "last_seen_at": t.last_seen_at.isoformat(),
                "max_confidence": round(agg.max_confidence, 3) if agg else None,
                "observation_count": agg.observation_count if agg else 0,
                "final_risk_score": round(t.final_risk_score, 1),
                "dominant_color": t.dominant_color,
            }
        )

    return {
        "job_id": job_id,
        "total_tracked_objects": counts["total_tracked_objects"],
        "class_counts": counts["class_counts"],
        "tracks": track_rows,
    }
