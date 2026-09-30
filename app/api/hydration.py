from __future__ import annotations

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from app.schemas.hydration import HydrationTargetResponse, HydrationTodayResponse
from app.services.hydration_service import HydrationService
from app.database.session import get_db
from app.services.auth_service import get_current_user


router = APIRouter(prefix="/hydration", tags=["hydration"])


@router.get("/target", response_model=HydrationTargetResponse)
def get_target(db: Session = Depends(get_db), user=Depends(get_current_user)) -> HydrationTargetResponse:
    service = HydrationService(db)
    try:
        data = service.calculate_target(user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HydrationTargetResponse(**data)


@router.get("/today", response_model=HydrationTodayResponse)
def get_today(db: Session = Depends(get_db), user=Depends(get_current_user)) -> HydrationTodayResponse:
    service = HydrationService(db)
    try:
        data = service.get_today(user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HydrationTodayResponse(**data)
