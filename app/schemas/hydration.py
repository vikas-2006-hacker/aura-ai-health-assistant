from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from typing import Optional
from datetime import date


class HydrationTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    target_ml: int
    basis: str
    explanation: Optional[str] = None


class HydrationTodayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date: date
    target_ml: int
    consumed_ml: int
    remaining_ml: int
    progress_percent: float
    status: str
