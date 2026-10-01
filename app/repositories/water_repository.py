from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.water_intake import WaterIntake


class WaterRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, user_id: int, amount_ml: int, consumed_at, source: Optional[str]) -> WaterIntake:
        wi = WaterIntake(user_id=user_id, amount_ml=amount_ml, consumed_at=consumed_at, source=source)
        self.db.add(wi)
        self.db.commit()
        self.db.refresh(wi)
        return wi

    def get_by_id(self, user_id: int, wi_id: int) -> Optional[WaterIntake]:
        return self.db.query(WaterIntake).filter(WaterIntake.id == wi_id, WaterIntake.user_id == user_id).one_or_none()

    def delete(self, user_id: int, wi_id: int) -> bool:
        wi = self.get_by_id(user_id, wi_id)
        if wi is None:
            return False
        self.db.delete(wi)
        self.db.commit()
        return True

    def get_today(self, user_id: int) -> List[WaterIntake]:
        today = datetime.now(timezone.utc).date()
        return (
            self.db.query(WaterIntake)
            .filter(func.date(WaterIntake.consumed_at) == today, WaterIntake.user_id == user_id)
            .order_by(WaterIntake.consumed_at.desc())
            .all()
        )

    def get_history(self, user_id: int, limit: int = 50, offset: int = 0) -> tuple[List[WaterIntake], int]:
        q = self.db.query(WaterIntake).filter(WaterIntake.user_id == user_id).order_by(WaterIntake.consumed_at.desc())
        total = q.count()
        items = q.limit(limit).offset(offset).all()
        return items, total
