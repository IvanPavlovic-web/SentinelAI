from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_current_user_for_streaming
from app.core.streaming import stream_video_file
from app.db.base import get_db
from app.schemas.video import ProcessingJobRead
from app.services import job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=ProcessingJobRead)
def get_job(job_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return job_service.get_job(db, job_id)


@router.get("/{job_id}/detections")
def get_job_detections(job_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """What the pipeline actually found in the footage for this job: object
    classes and counts, and per-track detail, independent of whether any
    zone/rule triggered an incident. Safe to poll while a job is still
    processing; rows are written incrementally."""
    return job_service.get_job_detections(db, job_id)


@router.get("/{job_id}/annotated-video")
def get_annotated_video(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_for_streaming),
):
    """The source video re-rendered with detection boxes/track IDs/risk
    scores burned in, exactly what the AI found, frame by frame. Only
    available once the job's tracking pass has finished."""
    job = job_service.get_job(db, job_id)
    if not job.annotated_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotated preview not available yet")
    return stream_video_file(job.annotated_path, request)


@router.get("/{job_id}/events")
def get_job_events(job_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Full live-activity narration log for this job, oldest first: what
    the Video Detail page's activity panel replays for a completed job.
    Safe to call mid-processing too; rows are written incrementally."""
    return job_service.get_job_events(db, job_id)


@router.get("/{job_id}/metrics")
def get_job_metrics(job_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    metrics = job_service.get_job_metrics(db, job_id)
    return [
        {
            "id": m.id,
            "total_frames": m.total_frames,
            "processed_frames": m.processed_frames,
            "duration_seconds": m.duration_seconds,
            "processing_fps": m.processing_fps,
            "avg_latency_ms": m.avg_latency_ms,
            "p95_latency_ms": m.p95_latency_ms,
            "avg_cpu_percent": m.avg_cpu_percent,
            "avg_ram_mb": m.avg_ram_mb,
            "queue_wait_seconds": m.queue_wait_seconds,
            "incident_count": m.incident_count,
            "created_at": m.created_at.isoformat(),
        }
        for m in metrics
    ]
