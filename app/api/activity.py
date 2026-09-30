from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.activity import ActivitySummaryResponse
from app.schemas.activity_features import ActivityFeaturesResponse
from app.services.activity_intelligence_service import ActivityIntelligenceService
from app.services.activity_feature_service import ActivityFeatureService
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/summary", response_model=ActivitySummaryResponse)
def activity_summary(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> ActivitySummaryResponse:
    summary = ActivityIntelligenceService(db).summarize_for_user(user.id, start_time, end_time)
    return ActivitySummaryResponse(**summary)


@router.get("/features", response_model=ActivityFeaturesResponse)
def activity_features(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> ActivityFeaturesResponse:
    try:
        features = ActivityFeatureService(db).extract_for_user(user.id, start_time, end_time)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ActivityFeaturesResponse(**features)
