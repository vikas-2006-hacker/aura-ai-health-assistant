from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.health_data import HealthDataCreate, HealthDataHistoryResponse, HealthDataResponse, HealthDataSummaryResponse, HealthDataTodayResponse
from app.services.auth_service import get_current_user
from app.services.health_data_service import HealthDataService

router = APIRouter(prefix="/health-data", tags=["health-data"])


@router.post("", response_model=HealthDataResponse, status_code=status.HTTP_201_CREATED)
def create_health_data(payload: HealthDataCreate, db: Session = Depends(get_db), user=Depends(get_current_user)) -> HealthDataResponse:
    entry = HealthDataService(db).create(user.id, **payload.dict())
    return HealthDataResponse.from_orm(entry)


@router.get("/today", response_model=HealthDataTodayResponse)
def get_today_health_data(db: Session = Depends(get_db), user=Depends(get_current_user)) -> HealthDataTodayResponse:
    return HealthDataTodayResponse(**HealthDataService(db).get_today(user.id))


@router.get("/history", response_model=HealthDataHistoryResponse)
def get_health_data_history(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db), user=Depends(get_current_user)) -> HealthDataHistoryResponse:
    return HealthDataHistoryResponse(**HealthDataService(db).get_history(user.id, limit, offset))


@router.get("/summary", response_model=HealthDataSummaryResponse)
def get_health_data_summary(db: Session = Depends(get_db), user=Depends(get_current_user)) -> HealthDataSummaryResponse:
    return HealthDataSummaryResponse(**HealthDataService(db).get_summary(user.id))
