from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_profile import UserProfile


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).one_or_none()

    def find_by_id(self, user_id: int) -> User | None:
        return self.db.query(User).get(user_id)

    def create_user(self, *, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_profile(self, user_id: int) -> UserProfile | None:
        return self.db.query(UserProfile).filter(UserProfile.user_id == user_id).one_or_none()

    def create_or_update_profile(self, user_id: int, **data) -> UserProfile:
        profile = self.get_profile(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id, **data)
            self.db.add(profile)
        else:
            for k, v in data.items():
                setattr(profile, k, v)
        self.db.commit()
        self.db.refresh(profile)
        return profile
