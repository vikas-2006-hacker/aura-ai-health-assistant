from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.schemas.auth import UserResponse, UserProfileCreate, UserProfileResponse
from app.services.auth_service import AuthService, get_current_user
from app.repositories.user_repository import UserRepository
from app.database.session import get_db
from sqlalchemy.orm import Session
from fastapi import Depends



router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def read_current_user(user: object = Depends(get_current_user)) -> UserResponse:
    return UserResponse.from_orm(user)


@router.post("/me/profile", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(payload: UserProfileCreate, db: Session = Depends(get_db), user=Depends(get_current_user)) -> UserProfileResponse:
    repo = UserRepository(db)
    profile = repo.create_or_update_profile(user_id=user.id, **payload.dict())
    return UserProfileResponse.from_orm(profile)


@router.get("/me/profile", response_model=UserProfileResponse)
def get_profile(db: Session = Depends(get_db), user=Depends(get_current_user)) -> UserProfileResponse:
    repo = UserRepository(db)
    profile = repo.get_profile(user.id)
    if profile is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return UserProfileResponse.from_orm(profile)
