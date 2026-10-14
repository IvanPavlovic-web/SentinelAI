from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.camera import JobStatus, ProcessingJob, VideoSource


def _validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_video_extensions_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed: {settings.allowed_video_extensions_list}",
        )
    return ext


def save_upload(upload_dir: Path, file: UploadFile) -> tuple[str, str, int]:
    """Validates and saves an uploaded video with a safe UUID filename.
    Returns (stored_filename, file_path, size_bytes)."""
    ext = _validate_extension(file.filename or "")
    stored_filename = f"{uuid.uuid4().hex}{ext}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / stored_filename

    size = 0
    # MAX_UPLOAD_SIZE_MB == 0 means unlimited (streamed straight to disk in
    # fixed-size chunks below, so there is no in-memory ceiling either way —
    # this only guards against accidentally filling the uploads volume).
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 if settings.MAX_UPLOAD_SIZE_MB > 0 else None
    with open(file_path, "wb") as out:
        while chunk := file.file.read(8 * 1024 * 1024):
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                out.close()
                file_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds max size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                )
            out.write(chunk)

    return stored_filename, str(file_path), size


def create_video_source_and_job(
    db: Session,
    camera_id: int | None,
    uploaded_by: int,
    original_filename: str,
    stored_filename: str,
    file_path: str,
    file_size_bytes: int,
) -> tuple[VideoSource, ProcessingJob]:
    video_source = VideoSource(
        camera_id=camera_id,
        uploaded_by=uploaded_by,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_path=file_path,
        file_size_bytes=file_size_bytes,
    )
    db.add(video_source)
    db.commit()
    db.refresh(video_source)

    job = ProcessingJob(video_source_id=video_source.id, status=JobStatus.PENDING)
    db.add(job)
    db.commit()
    db.refresh(job)

    return video_source, job


def list_videos(db: Session) -> list[VideoSource]:
    return db.query(VideoSource).order_by(VideoSource.created_at.desc()).all()


def get_video(db: Session, video_id: int) -> VideoSource:
    video = db.get(VideoSource, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video


def list_jobs_for_video(db: Session, video_id: int) -> list[ProcessingJob]:
    get_video(db, video_id)  # validate exists
    return (
        db.query(ProcessingJob)
        .filter(ProcessingJob.video_source_id == video_id)
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )


def create_reprocess_job(db: Session, video_id: int) -> ProcessingJob:
    get_video(db, video_id)  # validate exists
    job = ProcessingJob(video_source_id=video_id, status=JobStatus.PENDING)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
