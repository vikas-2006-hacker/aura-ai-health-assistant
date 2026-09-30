from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


class WaterIntakeCreate(BaseModel):
    amount_ml: int = Field(..., gt=0, le=100000, description="Amount in milliliters")
    consumed_at: Optional[datetime] = None
    source: Optional[str] = None


class WaterIntakeResponse(BaseModel):
    id: int
    user_id: int
    amount_ml: int
    consumed_at: datetime
    source: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class WaterTodayResponse(BaseModel):
    date: date
    total_ml: int
    entries: List[WaterIntakeResponse]


class WaterHistoryResponse(BaseModel):
    entries: List[WaterIntakeResponse]
    limit: int
    offset: int
    total: int
