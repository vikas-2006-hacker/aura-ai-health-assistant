from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.auth_service import get_current_user
from app.services.wellness_service import WellnessService

router = APIRouter(prefix="", tags=["wellness"])


@router.get("/insights/today", status_code=status.HTTP_200_OK)
def insights_today(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_today_insights(user.id)


@router.get("/recommendations", status_code=status.HTTP_200_OK)
def recommendations(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_recommendations(user.id)


@router.get("/notifications/preferences", status_code=status.HTTP_200_OK)
def notification_preferences(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_notification_preferences(user.id)


@router.post("/notifications/preferences", status_code=status.HTTP_200_OK)
def update_notification_preferences(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).update_notification_preferences(user.id, payload)


@router.get("/notifications", status_code=status.HTTP_200_OK)
def notifications(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_notifications(user.id)


@router.get("/insights/changes", status_code=status.HTTP_200_OK)
def insights_changes(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_change_insights(user.id)


@router.get("/insights/recovery", status_code=status.HTTP_200_OK)
def insights_recovery(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_recovery_insights(user.id)


@router.get("/insights/hydration", status_code=status.HTTP_200_OK)
def insights_hydration(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_hydration_insights(user.id)
