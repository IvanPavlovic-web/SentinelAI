from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_current_user_for_streaming, require_roles
from app.db.base import get_db
from app.schemas.camera import CameraCreate, CameraRead, CameraSnapshotInfo, CameraTestConnectionRequest, CameraUpdate
from app.schemas.video import ProcessingJobRead
from app.services import camera_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraRead])
def list_cameras(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return [
        CameraRead.model_validate(camera).model_copy(update={"latest_job_status": job_status.value if job_status else None})
        for camera, job_status in camera_service.list_cameras_with_latest_job_status(db)
    ]


@router.post("", response_model=CameraRead, status_code=201)
def create_camera(
    payload: CameraCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    camera = camera_service.create_camera(db, payload, owner_id=current_user.id)
    log_action(db, current_user.id, "camera_create", "camera", camera.id)
    return camera


@router.patch("/{camera_id}", response_model=CameraRead)
def update_camera(
    camera_id: int,
    payload: CameraUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    return camera_service.update_camera(db, camera_id, payload)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin")),
):
    camera_service.delete_camera(db, camera_id)
    log_action(db, current_user.id, "camera_delete", "camera", camera_id)
    return None


@router.post("/test-connection")
def test_connection(
    payload: CameraTestConnectionRequest,
    current_user=Depends(require_roles("admin", "analyst")),
):
    """Tries to open the given stream URL (RTSP, or any source OpenCV can
    read) and confirms a frame can actually be read, without starting a
    monitoring session. Used by the Add Camera form before saving."""
    return camera_service.test_connection(payload.rtsp_url)


@router.post("/{camera_id}/start", response_model=ProcessingJobRead, status_code=201)
def start_monitoring(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    job = camera_service.start_live_session(db, camera_id)
    log_action(db, current_user.id, "camera_start", "camera", camera_id)
    return job


@router.post("/{camera_id}/stop", response_model=ProcessingJobRead)
def stop_monitoring(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    job = camera_service.stop_live_session(db, camera_id)
    log_action(db, current_user.id, "camera_stop", "camera", camera_id)
    return job


@router.get("/{camera_id}/jobs", response_model=list[ProcessingJobRead])
def list_camera_jobs(camera_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Every monitoring session ever run for this camera, newest first."""
    return camera_service.list_jobs_for_camera(db, camera_id)


@router.get("/{camera_id}/snapshot-info", response_model=CameraSnapshotInfo)
def get_snapshot_info(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Freshness metadata for the live snapshot: when it was last actually
    refreshed. The live-camera loop only overwrites the snapshot file when
    the source frame genuinely changed (see app/workers/tasks.py's
    unchanged-frame skip), so the file's mtime is exactly "when this
    picture last changed" -- useful for showing "updated Xs ago" in the
    UI, since many public webcams (see app/seed.py) only refresh every
    few minutes and would otherwise look frozen/broken."""
    camera_service.get_camera(db, camera_id)  # 404s cleanly if the camera doesn't exist
    path = camera_service.live_snapshot_path(camera_id)
    if not path.is_file():
        return CameraSnapshotInfo(exists=False, last_updated=None)
    return CameraSnapshotInfo(exists=True, last_updated=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc))


@router.get("/{camera_id}/snapshot")
def get_snapshot(
    camera_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_for_streaming),
):
    """The most recently captured frame from this camera's live session,
    with detection boxes burned in -- refreshed roughly once per sampled
    frame while monitoring is active. This is the "live view" for a
    camera: a frequently-polled still image rather than a video stream
    (see README "Live cameras" for the reasoning)."""
    camera_service.get_camera(db, camera_id)  # 404s cleanly if the camera doesn't exist
    path = camera_service.live_snapshot_path(camera_id)
    if not path.is_file():
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No snapshot yet; start monitoring first")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
