from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.health_data import HealthData


class HealthDataRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, *, user_id: int, metric_type: str, value: float, unit: str, source: str, recorded_at: datetime) -> HealthData:
        entry = HealthData(user_id=user_id, metric_type=metric_type, value=value, unit=unit, source=source, recorded_at=recorded_at)
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def get_today(self, user_id: int) -> list[HealthData]:
        return self.db.query(HealthData).filter(HealthData.user_id == user_id, func.date(HealthData.recorded_at) == date.today()).order_by(HealthData.recorded_at.desc()).all()

    def get_history(self, user_id: int, limit: int, offset: int) -> tuple[list[HealthData], int]:
        query = self.db.query(HealthData).filter(HealthData.user_id == user_id).order_by(HealthData.recorded_at.desc())
        return query.limit(limit).offset(offset).all(), query.count()

    def get_today_summary(self, user_id: int) -> dict[str, float]:
        rows = self.db.query(HealthData.metric_type, func.sum(HealthData.value)).filter(HealthData.user_id == user_id, func.date(HealthData.recorded_at) == date.today()).group_by(HealthData.metric_type).all()
        return {metric_type: float(total) for metric_type, total in rows}
