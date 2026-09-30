from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SensorDataType = Literal["steps", "activity_duration"]
SensorSourcePlatform = Literal["healthkit", "health_connect", "manual"]
SensorSourceType = Literal["phone", "wearable", "manual"]

_CANONICAL_UNITS = {"steps": "count", "activity_duration": "seconds"}


class SensorRecordCreate(BaseModel):
    source_platform: SensorSourcePlatform
    source_type: SensorSourceType
    data_type: SensorDataType
    value: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=20)
    start_time: datetime
    end_time: datetime
    source_record_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=255)
    device_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        allowed_keys = {
            "aggregation",
            "device_model",
            "entry_method",
            "original_unit",
            "recording_method",
            "source_id",
            "source_name",
            "synced_at",
        }
        if len(value) > 8 or not set(value).issubset(allowed_keys):
            raise ValueError("metadata contains unsupported fields")
        for item in value.values():
            if isinstance(item, str) and len(item) > 512:
                raise ValueError("metadata string values must be at most 512 characters")
            if isinstance(item, (dict, list)):
                raise ValueError("metadata values must be scalar")
            if isinstance(item, float) and not isfinite(item):
                raise ValueError("metadata numeric values must be finite")
        return value

    @model_validator(mode="after")
    def validate_normalized_record(self) -> "SensorRecordCreate":
        if self.unit != _CANONICAL_UNITS[self.data_type]:
            raise ValueError(f"{self.data_type} must use unit {_CANONICAL_UNITS[self.data_type]!r}")
        if not isfinite(self.value):
            raise ValueError("value must be finite")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.data_type == "steps" and not self.value.is_integer():
            raise ValueError("steps must be a whole-number count")
        if self.source_record_id is None and self.idempotency_key is None:
            raise ValueError("source_record_id or idempotency_key is required")
        return self


class SensorRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    source_platform: SensorSourcePlatform
    source_type: SensorSourceType
    data_type: SensorDataType
    value: float
    unit: str
    start_time: datetime
    end_time: datetime
    source_record_id: Optional[str]
    device_id: Optional[str]
    confidence: Optional[float]
    metadata: Optional[dict[str, Any]] = Field(default=None, validation_alias="record_metadata")
    validation_status: str
    created_at: datetime
    updated_at: datetime


class SensorIngestionResponse(BaseModel):
    status: Literal["accepted", "duplicate"]
    record_id: int
    duplicate: bool


class SensorRecordListResponse(BaseModel):
    entries: list[SensorRecordResponse]
    limit: int
    offset: int
    total: int


class SensorBatchCreate(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class SensorBatchItemResponse(BaseModel):
    status: Literal["accepted", "duplicate", "rejected"]
    record_id: Optional[int] = None
    errors: list[str] = Field(default_factory=list)


class SensorBatchResponse(BaseModel):
    accepted_count: int
    duplicate_count: int
    rejected_count: int
    records: list[SensorBatchItemResponse]
    synchronization_status: Literal["complete", "partial", "failed"]
