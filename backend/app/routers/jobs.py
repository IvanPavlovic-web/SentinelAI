from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.schemas.video import ProcessingJobRead
from app.services import job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=ProcessingJobRead)
def get_job(job_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return job_service.get_job(db, job_id)


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
