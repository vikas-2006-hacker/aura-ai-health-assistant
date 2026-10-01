from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.notification_preferences import (
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
)
from app.services.auth_service import get_current_user
from app.services.wellness_service import WellnessService

router = APIRouter(prefix="", tags=["wellness"])


@router.get("/insights/today", status_code=status.HTTP_200_OK)
def insights_today(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_today_insights(user.id)


@router.get("/recommendations", status_code=status.HTTP_200_OK)
def recommendations(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_recommendations(user.id)


@router.get(
    "/notifications/preferences",
    status_code=status.HTTP_200_OK,
    response_model=NotificationPreferencesResponse,
)
def notification_preferences(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_notification_preferences(user.id)


@router.post(
    "/notifications/preferences",
    status_code=status.HTTP_200_OK,
    response_model=NotificationPreferencesResponse,
)
@router.patch(
    "/notifications/preferences",
    status_code=status.HTTP_200_OK,
    response_model=NotificationPreferencesResponse,
)
def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    return WellnessService(db).update_notification_preferences(
        user.id,
        payload.model_dump(exclude_unset=True),
    )


@router.get("/notifications", status_code=status.HTTP_200_OK)
def notifications(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_notifications(user.id)


@router.get("/notifications/unread", status_code=status.HTTP_200_OK)
def unread_notifications(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_unread_notifications(user.id)


@router.patch("/notifications/{notification_id}/read", status_code=status.HTTP_200_OK)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    result = WellnessService(db).mark_notification_read(user.id, notification_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return result


@router.get("/insights/changes", status_code=status.HTTP_200_OK)
def insights_changes(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_change_insights(user.id)


@router.get("/insights/recovery", status_code=status.HTTP_200_OK)
def insights_recovery(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_recovery_insights(user.id)


@router.get("/insights/hydration", status_code=status.HTTP_200_OK)
def insights_hydration(db: Session = Depends(get_db), user=Depends(get_current_user)) -> dict:
    return WellnessService(db).get_hydration_insights(user.id)
