from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user, require_roles
from app.db.base import get_db
from app.schemas.video import ProcessingJobRead, VideoSourceRead, VideoUploadResponse
from app.services import video_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.get("", response_model=list[VideoSourceRead])
def list_videos(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return video_service.list_videos(db)


@router.post("/upload", response_model=VideoUploadResponse, status_code=201)
def upload_video(
    file: UploadFile = File(...),
    camera_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    upload_dir = Path(settings.UPLOAD_DIR)
    stored_filename, file_path, size = video_service.save_upload(upload_dir, file)

    video_source, job = video_service.create_video_source_and_job(
        db,
        camera_id=camera_id,
        uploaded_by=current_user.id,
        original_filename=file.filename or stored_filename,
        stored_filename=stored_filename,
        file_path=file_path,
        file_size_bytes=size,
    )

    log_action(db, current_user.id, "video_upload", "video_source", video_source.id)

    # Enqueue the Celery processing task (best-effort: if Celery/Redis is
    # unreachable in this environment, the job stays PENDING and can be
    # triggered again via POST /api/videos/{id}/process).
    try:
        from app.workers.tasks import process_video_task

        process_video_task.delay(job.id)
    except Exception:  # noqa: BLE001 - broker may be unavailable in dev/CS50 grading
        pass

    return VideoUploadResponse(video_source=video_source, processing_job=job)


@router.get("/{video_id}", response_model=VideoSourceRead)
def get_video(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return video_service.get_video(db, video_id)


@router.get("/{video_id}/jobs", response_model=list[ProcessingJobRead])
def list_video_jobs(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """All processing jobs ever run for this video, newest first — lets the
    frontend find and subscribe to the latest job's live progress without
    requiring the user to manually trigger reprocessing first."""
    return video_service.list_jobs_for_video(db, video_id)


@router.post("/{video_id}/process", response_model=ProcessingJobRead, status_code=201)
def reprocess_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    job = video_service.create_reprocess_job(db, video_id)
    try:
        from app.workers.tasks import process_video_task

        process_video_task.delay(job.id)
    except Exception:  # noqa: BLE001
        pass
    return job
