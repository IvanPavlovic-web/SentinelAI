from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.models.camera import Camera, JobStatus, ProcessingJob
from app.schemas.camera import CameraCreate, CameraUpdate


def list_cameras(db: Session) -> list[Camera]:
    return db.query(Camera).order_by(Camera.created_at.desc()).all()


def list_cameras_with_latest_job_status(db: Session) -> list[tuple[Camera, JobStatus | None]]:
    """Every camera paired with its most recent job's status, in exactly
    two queries total regardless of camera count or how many historical
    job rows each camera has accumulated (a live camera re-queues a new
    job row roughly every LIVE_SESSION_MAX_SECONDS, so that history grows
    without bound over a camera's lifetime). The frontend's camera list
    used to get this per-camera via one GET /api/cameras/{id}/jobs call
    per row -- an N+1 against the API -- just to render a status chip."""
    cameras = list_cameras(db)
    if not cameras:
        return []
    camera_ids = [c.id for c in cameras]

    row_number = func.row_number().over(
        partition_by=ProcessingJob.camera_id, order_by=ProcessingJob.created_at.desc()
    ).label("rn")
    ranked = select(ProcessingJob, row_number).where(ProcessingJob.camera_id.in_(camera_ids)).subquery()
    latest_job = aliased(ProcessingJob, ranked)
    latest_jobs = db.execute(select(latest_job).where(ranked.c.rn == 1)).scalars().all()
    status_by_camera = {job.camera_id: job.status for job in latest_jobs}

    return [(camera, status_by_camera.get(camera.id)) for camera in cameras]


def get_camera(db: Session, camera_id: int) -> Camera:
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


def create_camera(db: Session, payload: CameraCreate, owner_id: int) -> Camera:
    camera = Camera(**payload.model_dump(), owner_id=owner_id)
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return camera


def update_camera(db: Session, camera_id: int, payload: CameraUpdate) -> Camera:
    camera = get_camera(db, camera_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(camera, field, value)
    db.commit()
    db.refresh(camera)
    return camera


def delete_camera(db: Session, camera_id: int) -> None:
    camera = get_camera(db, camera_id)
    snapshot_path = live_snapshot_path(camera_id)
    db.delete(camera)  # cascades to video_sources, zones, processing_jobs (and their own cascades)
    db.commit()
    snapshot_path.unlink(missing_ok=True)


def test_connection(rtsp_url: str) -> dict:
    """Opens the given stream URL just long enough to confirm it works and
    read its basic properties, without starting a monitoring session."""
    import cv2

    cap = cv2.VideoCapture(rtsp_url)
    try:
        if not cap.isOpened():
            return {"ok": False, "detail": "Could not open stream"}
        ok, _frame = cap.read()
        if not ok:
            return {"ok": False, "detail": "Stream opened but no frame could be read"}
        return {
            "ok": True,
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None,
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None,
            "fps": cap.get(cv2.CAP_PROP_FPS) or None,
        }
    finally:
        cap.release()


def live_snapshot_path(camera_id: int) -> Path:
    return Path(settings.UPLOAD_DIR) / "live" / f"camera_{camera_id}_latest.jpg"


def get_active_job(db: Session, camera_id: int) -> ProcessingJob | None:
    return (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.camera_id == camera_id,
            ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.PROCESSING]),
        )
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )


def list_jobs_for_camera(db: Session, camera_id: int) -> list[ProcessingJob]:
    get_camera(db, camera_id)  # validate exists
    return (
        db.query(ProcessingJob)
        .filter(ProcessingJob.camera_id == camera_id)
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )


def start_live_session(db: Session, camera_id: int) -> ProcessingJob:
    camera = get_camera(db, camera_id)
    if not camera.rtsp_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Camera has no stream URL configured")
    if get_active_job(db, camera_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This camera already has an active monitoring session")

    camera.is_active = True
    job = ProcessingJob(camera_id=camera_id, is_live=True, status=JobStatus.PENDING)
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        from app.workers.tasks import process_live_camera_task

        process_live_camera_task.delay(job.id)
    except Exception:  # noqa: BLE001 - broker may be unavailable in dev/CS50 grading
        pass

    return job


def stop_live_session(db: Session, camera_id: int) -> ProcessingJob:
    camera = get_camera(db, camera_id)
    camera.is_active = False
    job = get_active_job(db, camera_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This camera has no active monitoring session")
    job.stop_requested = True
    db.commit()
    db.refresh(job)
    return job
