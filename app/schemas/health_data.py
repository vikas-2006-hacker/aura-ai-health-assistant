from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

MetricType = Literal["steps", "activity", "workouts", "sleep", "calories"]
HealthSource = Literal["mobile", "manual", "smartwatch"]


class HealthDataCreate(BaseModel):
    metric_type: MetricType
    value: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=50)
    source: HealthSource
    recorded_at: Optional[datetime] = None


class HealthDataResponse(BaseModel):
    id: int
    user_id: int
    metric_type: MetricType
    value: float
    unit: str
    source: HealthSource
    recorded_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class HealthDataTodayResponse(BaseModel):
    date: date
    entries: list[HealthDataResponse]


class HealthDataHistoryResponse(BaseModel):
    entries: list[HealthDataResponse]
    limit: int
    offset: int
    total: int


class HealthDataSummaryResponse(BaseModel):
    date: date
    metrics: dict[MetricType, float]
