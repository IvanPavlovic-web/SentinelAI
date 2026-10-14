from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_roles
from app.db.base import get_db
from app.schemas.zone import ZoneCreate, ZoneRead, ZoneUpdate
from app.services import zone_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/zones", tags=["zones"])


def _to_read(zone) -> ZoneRead:
    return ZoneRead(
        id=zone.id,
        camera_id=zone.camera_id,
        name=zone.name,
        severity=zone.severity,
        polygon=[tuple(p) for p in json.loads(zone.polygon_json)],
        minimum_dwell_seconds=zone.minimum_dwell_seconds,
        is_active=zone.is_active,
        created_at=zone.created_at,
        updated_at=zone.updated_at,
    )


@router.get("", response_model=list[ZoneRead])
def list_zones(
    camera_id: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return [_to_read(z) for z in zone_service.list_zones(db, camera_id)]


@router.post("", response_model=ZoneRead, status_code=201)
def create_zone(
    payload: ZoneCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    zone = zone_service.create_zone(db, payload)
    log_action(db, current_user.id, "zone_create", "zone", zone.id)
    return _to_read(zone)


@router.patch("/{zone_id}", response_model=ZoneRead)
def update_zone(
    zone_id: int,
    payload: ZoneUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    zone = zone_service.update_zone(db, zone_id, payload)
    return _to_read(zone)


@router.delete("/{zone_id}", status_code=204)
def delete_zone(
    zone_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin")),
):
    zone_service.delete_zone(db, zone_id)
    log_action(db, current_user.id, "zone_delete", "zone", zone_id)
    return None
