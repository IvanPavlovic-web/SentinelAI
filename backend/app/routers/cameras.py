from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_roles
from app.db.base import get_db
from app.schemas.camera import CameraCreate, CameraRead, CameraUpdate
from app.services import camera_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraRead])
def list_cameras(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return camera_service.list_cameras(db)


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
