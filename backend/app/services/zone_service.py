from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.zone import Rule, Zone
from app.schemas.zone import RuleCreate, RuleUpdate, ZoneCreate, ZoneUpdate


def _zone_to_dict_polygon(zone: Zone) -> list[tuple[float, float]]:
    return [tuple(p) for p in json.loads(zone.polygon_json)]


def list_zones(db: Session, camera_id: int | None = None) -> list[Zone]:
    query = db.query(Zone)
    if camera_id is not None:
        query = query.filter(Zone.camera_id == camera_id)
    return query.order_by(Zone.created_at.desc()).all()


def get_zone(db: Session, zone_id: int) -> Zone:
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    return zone


def create_zone(db: Session, payload: ZoneCreate) -> Zone:
    zone = Zone(
        camera_id=payload.camera_id,
        name=payload.name,
        severity=payload.severity,
        polygon_json=json.dumps(payload.polygon),
        minimum_dwell_seconds=payload.minimum_dwell_seconds,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def update_zone(db: Session, zone_id: int, payload: ZoneUpdate) -> Zone:
    zone = get_zone(db, zone_id)
    data = payload.model_dump(exclude_unset=True)
    if "polygon" in data:
        zone.polygon_json = json.dumps(data.pop("polygon"))
    for field, value in data.items():
        setattr(zone, field, value)
    db.commit()
    db.refresh(zone)
    return zone


def delete_zone(db: Session, zone_id: int) -> None:
    zone = get_zone(db, zone_id)
    db.delete(zone)
    db.commit()


def list_rules(db: Session, zone_id: int | None = None) -> list[Rule]:
    query = db.query(Rule)
    if zone_id is not None:
        query = query.filter(Rule.zone_id == zone_id)
    return query.order_by(Rule.created_at.desc()).all()


def create_rule(db: Session, payload: RuleCreate) -> Rule:
    get_zone(db, payload.zone_id)  # validate zone exists
    rule = Rule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def get_rule(db: Session, rule_id: int) -> Rule:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule


def update_rule(db: Session, rule_id: int, payload: RuleUpdate) -> Rule:
    rule = get_rule(db, rule_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule
