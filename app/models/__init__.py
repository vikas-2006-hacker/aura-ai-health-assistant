"""Database models package.

Import models here so Alembic autogenerate and other tooling see them by
importing the package (e.g. ``from app.models import User``).
"""

from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.water_intake import WaterIntake
from app.models.health_data import HealthData
from app.models.sensor_record import SensorRecord, SensorSyncRecord
from app.models.wellness import NotificationPreference, NotificationRecord, RecommendationRecord

__all__ = [
    "User",
    "UserProfile",
    "WaterIntake",
    "HealthData",
    "SensorRecord",
    "SensorSyncRecord",
    "NotificationPreference",
    "NotificationRecord",
    "RecommendationRecord",
]
