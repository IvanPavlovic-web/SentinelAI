from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.schemas.dashboard import DashboardPerformance, DashboardSummary, IncidentAnalytics
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return dashboard_service.get_summary(db)


@router.get("/performance", response_model=DashboardPerformance)
def performance(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return DashboardPerformance(points=dashboard_service.get_performance(db))


@router.get("/analytics", response_model=IncidentAnalytics)
def analytics(days: int = 14, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return dashboard_service.get_incident_analytics(db, days=days)
