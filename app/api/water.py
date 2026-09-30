from __future__ import annotations

from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from app.schemas.water import (
    WaterIntakeCreate,
    WaterIntakeResponse,
    WaterTodayResponse,
    WaterHistoryResponse,
)
from app.services.water_service import WaterService
from app.database.session import get_db
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/water", tags=["water"])


@router.post("", response_model=WaterIntakeResponse, status_code=status.HTTP_201_CREATED)
def create_water(payload: WaterIntakeCreate, db: Session = Depends(get_db), user=Depends(get_current_user)) -> WaterIntakeResponse:
    service = WaterService(db)
    try:
        wi = service.create_intake(user_id=user.id, amount_ml=payload.amount_ml, consumed_at=payload.consumed_at, source=payload.source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return WaterIntakeResponse.from_orm(wi)


@router.get("/today", response_model=WaterTodayResponse)
def get_today(db: Session = Depends(get_db), user=Depends(get_current_user)) -> WaterTodayResponse:
    service = WaterService(db)
    data = service.get_today(user_id=user.id)
    # Pydantic will serialize date and entries
    return WaterTodayResponse(date=data["date"], total_ml=data["total_ml"], entries=data["entries"])


@router.get("/history", response_model=WaterHistoryResponse)
def get_history(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db), user=Depends(get_current_user)) -> WaterHistoryResponse:
    service = WaterService(db)
    data = service.get_history(user_id=user.id, limit=limit, offset=offset)
    return WaterHistoryResponse(entries=data["entries"], limit=data["limit"], offset=data["offset"], total=data["total"])


@router.delete("/{water_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_water(water_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)) -> None:
    service = WaterService(db)
    ok = service.delete_intake(user_id=user.id, wi_id=water_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return None
