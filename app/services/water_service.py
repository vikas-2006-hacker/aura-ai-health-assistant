from __future__ import annotations

from datetime import datetime, date
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.repositories.water_repository import WaterRepository
from app.models.water_intake import WaterIntake


class WaterService:
    def __init__(self, db: Session) -> None:
        self.repo = WaterRepository(db)

    def create_intake(self, user_id: int, amount_ml: int, consumed_at: datetime | None = None, source: str | None = None) -> WaterIntake:
        if amount_ml <= 0:
            raise ValueError("amount_ml must be > 0")
        if consumed_at is None:
            consumed_at = datetime.utcnow()
        return self.repo.create(user_id=user_id, amount_ml=amount_ml, consumed_at=consumed_at, source=source)

    def get_today(self, user_id: int) -> dict:
        entries = self.repo.get_today(user_id)
        total = sum(e.amount_ml for e in entries)
        return {"date": date.today(), "total_ml": total, "entries": entries}

    def get_history(self, user_id: int, limit: int = 50, offset: int = 0):
        items, total = self.repo.get_history(user_id, limit=limit, offset=offset)
        return {"entries": items, "limit": limit, "offset": offset, "total": total}

    def delete_intake(self, user_id: int, wi_id: int) -> bool:
        return self.repo.delete(user_id, wi_id)
