from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from typing import Optional
from datetime import date


class HydrationTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    target_ml: int
    basis: str
    base_target_ml: Optional[int] = None
    activity_level: Optional[str] = None
    activity_adjustment_percent: Optional[float] = None
    activity_adjustment_ml: Optional[int] = None
    explanation: Optional[str] = None


class HydrationTodayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date: date
    target_ml: int
    consumed_ml: int
    remaining_ml: int
    progress_percent: float
    status: str
    basis: Optional[str] = None
    base_target_ml: Optional[int] = None
    activity_level: Optional[str] = None
    activity_adjustment_percent: Optional[float] = None
    activity_adjustment_ml: Optional[int] = None
    explanation: Optional[str] = None
