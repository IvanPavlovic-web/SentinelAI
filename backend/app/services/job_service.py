from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.camera import ProcessingJob
from app.models.incident import PerformanceMetric


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
