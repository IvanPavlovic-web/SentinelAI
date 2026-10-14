from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.schemas.incident import IncidentRead, IncidentStatusUpdate, PaginatedIncidents
from app.services import incident_service

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("", response_model=PaginatedIncidents)
def list_incidents(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    status: str | None = None,
    priority: str | None = None,
    camera_id: int | None = None,
    processing_job_id: int | None = None,
    object_class: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    items, total = incident_service.list_incidents(
        db,
        page=page,
        page_size=page_size,
        status_filter=status,
        priority_filter=priority,
        camera_id=camera_id,
        processing_job_id=processing_job_id,
        object_class=object_class,
        date_from=date_from,
        date_to=date_to,
    )
    return PaginatedIncidents(items=items, total=total, page=page, page_size=page_size)


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(incident_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return incident_service.get_incident(db, incident_id)


@router.patch("/{incident_id}/status", response_model=IncidentRead)
def update_incident_status(
    incident_id: int,
    payload: IncidentStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return incident_service.update_incident_status(db, incident_id, payload, current_user.id)
