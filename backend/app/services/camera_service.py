from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.camera import Camera
from app.schemas.camera import CameraCreate, CameraUpdate


def list_cameras(db: Session) -> list[Camera]:
    return db.query(Camera).order_by(Camera.created_at.desc()).all()


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
    db.delete(camera)
    db.commit()
