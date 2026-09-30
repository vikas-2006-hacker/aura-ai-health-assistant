from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ActivityClassification = Literal["sedentary", "light", "moderate", "high"]
ActivityClassificationType = Literal["rule_based"]


class ActivitySummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    steps: int = 0
    activity_duration_seconds: float = 0.0
    active_intervals: int = 0
    longest_active_interval_seconds: float = 0.0
    steps_per_minute: float = 0.0
    classification: ActivityClassification
    classification_type: ActivityClassificationType = "rule_based"
    explanation: str
    confidence: Optional[float] = None
    source_types: list[Literal["wearable", "phone", "manual"]] = Field(default_factory=list)
    period_start: datetime
    period_end: datetime
