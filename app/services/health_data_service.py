from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.repositories.health_data_repository import HealthDataRepository


class HealthDataService:
    def __init__(self, db: Session) -> None:
        self.repository = HealthDataRepository(db)

    def create(self, user_id: int, *, metric_type: str, value: float, unit: str, source: str, recorded_at: datetime | None):
        return self.repository.create(user_id=user_id, metric_type=metric_type, value=value, unit=unit, source=source, recorded_at=recorded_at or datetime.utcnow())

    def get_today(self, user_id: int) -> dict:
        return {"date": date.today(), "entries": self.repository.get_today(user_id)}

    def get_history(self, user_id: int, limit: int, offset: int) -> dict:
        entries, total = self.repository.get_history(user_id, limit, offset)
        return {"entries": entries, "limit": limit, "offset": offset, "total": total}

    def get_summary(self, user_id: int) -> dict:
        return {"date": date.today(), "metrics": self.repository.get_today_summary(user_id)}
