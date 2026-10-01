from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

_TIME_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


class NotificationQuietHoursUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: Optional[StrictStr] = Field(default=None, pattern=_TIME_PATTERN)
    end: Optional[StrictStr] = Field(default=None, pattern=_TIME_PATTERN)

    @model_validator(mode="before")
    @classmethod
    def reject_null_and_empty_updates(cls, value):
        if not isinstance(value, dict) or not value:
            raise ValueError("quiet_hours must include start and/or end")
        if any(item is None for item in value.values()):
            raise ValueError("quiet-hour values cannot be null")
        return value


class NotificationPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notifications_enabled: Optional[StrictBool] = None
    hydration_notifications: Optional[StrictBool] = None
    activity_notifications: Optional[StrictBool] = None
    recovery_notifications: Optional[StrictBool] = None
    wellness_notifications: Optional[StrictBool] = None
    quiet_hours: Optional[NotificationQuietHoursUpdate] = None
    maximum_notification_frequency: Optional[StrictInt] = Field(default=None, ge=0, le=10)

    @model_validator(mode="before")
    @classmethod
    def require_non_null_preference_update(cls, value):
        if not isinstance(value, dict) or not value:
            raise ValueError("at least one notification preference must be provided")
        if any(item is None for item in value.values()):
            raise ValueError("notification preference values cannot be null")
        return value


class NotificationQuietHoursResponse(BaseModel):
    start: str
    end: str


class NotificationPreferencesResponse(BaseModel):
    notifications_enabled: bool
    hydration_notifications: bool
    activity_notifications: bool
    recovery_notifications: bool
    wellness_notifications: bool
    quiet_hours: NotificationQuietHoursResponse
    maximum_notification_frequency: int
