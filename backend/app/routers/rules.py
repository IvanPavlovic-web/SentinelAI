from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_roles
from app.db.base import get_db
from app.schemas.zone import RuleCreate, RuleRead, RuleUpdate
from app.services import zone_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=list[RuleRead])
def list_rules(
    zone_id: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return zone_service.list_rules(db, zone_id)


@router.post("", response_model=RuleRead, status_code=201)
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    rule = zone_service.create_rule(db, payload)
    log_action(db, current_user.id, "rule_create", "rule", rule.id)
    return rule


@router.patch("/{rule_id}", response_model=RuleRead)
def update_rule(
    rule_id: int,
    payload: RuleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "analyst")),
):
    rule = zone_service.update_rule(db, rule_id, payload)
    log_action(db, current_user.id, "rule_update", "rule", rule.id)
    return rule
