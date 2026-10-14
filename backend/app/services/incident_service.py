from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.incident import Incident, IncidentStatus
from app.schemas.incident import IncidentStatusUpdate
from app.services.audit_service import log_action


def list_incidents(
    db: Session,
    page: int = 1,
    page_size: int = 25,
    status_filter: str | None = None,
    priority_filter: str | None = None,
    camera_id: int | None = None,
    object_class: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[Incident], int]:
    query = db.query(Incident)

    if status_filter:
        query = query.filter(Incident.status == status_filter)
    if priority_filter:
        query = query.filter(Incident.priority == priority_filter)
    if camera_id is not None:
        query = query.filter(Incident.camera_id == camera_id)
    if object_class:
        query = query.filter(Incident.object_class == object_class)
    if date_from:
        query = query.filter(Incident.detected_at >= date_from)
    if date_to:
        query = query.filter(Incident.detected_at <= date_to)

    query = query.order_by(Incident.detected_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def get_incident(db: Session, incident_id: int) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


def update_incident_status(db: Session, incident_id: int, payload: IncidentStatusUpdate, user_id: int) -> Incident:
    incident = get_incident(db, incident_id)
    old_status = incident.status
    incident.status = payload.status
    incident.resolution_notes = payload.resolution_notes

    if payload.status in (IncidentStatus.RESOLVED, IncidentStatus.DISMISSED):
        incident.resolved_by = user_id
        incident.resolved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(incident)

    log_action(
        db,
        user_id=user_id,
        action="incident_status_change",
        resource_type="incident",
        resource_id=incident.id,
        details=f"{old_status.value} -> {incident.status.value}",
    )
    return incident
