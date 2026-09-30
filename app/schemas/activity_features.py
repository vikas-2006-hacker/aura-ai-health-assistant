from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


FeatureQualityStatus = Literal["valid", "invalid", "insufficient_data"]


class ActivityFeatureVector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_duration_seconds: float = Field(ge=0)
    window_hour_of_day: float = Field(ge=0, lt=24)
    window_day_of_week: int = Field(ge=1, le=7)
    total_steps: float = Field(ge=0)
    activity_duration_seconds: float = Field(ge=0)
    active_interval_count: int = Field(ge=0)
    average_steps_per_minute: float = Field(ge=0)
    maximum_steps_per_minute: float = Field(ge=0)
    active_to_window_ratio: float = Field(ge=0, le=1)
    steps_per_active_second: float = Field(ge=0)
    activity_density: float = Field(ge=0)
    mean_active_interval_seconds: float = Field(ge=0)
    maximum_active_interval_seconds: float = Field(ge=0)


class ActivityFeatureQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FeatureQualityStatus
    source_completeness: float = Field(ge=0, le=1)
    timestamp_validity: Literal["valid", "invalid"]
    duplicate_count: int = Field(ge=0)
    overlap_adjustment_seconds: float = Field(ge=0)
    missing_feature_count: int = Field(ge=0)
    missing_features: list[str] = Field(default_factory=list)
    invalid_record_count: int = Field(ge=0)
    valid_record_count: int = Field(ge=0)


class ActivityFeaturesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feature_version: str
    window_start: datetime
    window_end: datetime
    features: ActivityFeatureVector
    quality: ActivityFeatureQuality
