from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict
from sqlalchemy.orm import Session

from app.services.hydration_engine import HydrationEngine
from app.services.activity_intelligence_service import ActivityIntelligenceService
from app.repositories.user_repository import UserRepository
from app.repositories.water_repository import WaterRepository
from app.core.config import settings


class HydrationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.water_repo = WaterRepository(db)

    def _get_profile_or_raise(self, user_id: int):
        profile = self.user_repo.get_profile(user_id)
        if profile is None:
            raise ValueError("Profile not found; please create your user profile with weight_kg.")
        return profile

    def calculate_target(self, user_id: int) -> Dict:
        profile = self._get_profile_or_raise(user_id)
        weight = profile.weight_kg
        if weight is None:
            raise ValueError("Profile is missing weight_kg. Please complete your profile.")
        base = HydrationEngine.calculate_base_target_ml(weight, settings.water_ml_per_kg)
        today = date.today()
        period_start = datetime.combine(today, time.min)
        activity = ActivityIntelligenceService(self.db).summarize_for_user(
            user_id,
            period_start,
            period_start + timedelta(days=1),
        )
        activity_level = (
            activity["classification"]
            if activity["steps"] > 0 or activity["activity_duration_seconds"] > 0
            else profile.activity_level
        )
        target = HydrationEngine.apply_activity_adjustment(base, activity_level, settings.activity_adjustments)
        return {"target_ml": int(target), "basis": "weight_based", "explanation": "Target is calculated using a configurable application baseline (ml/kg) and the user's profile."}

    def get_today(self, user_id: int) -> Dict:
        profile = self._get_profile_or_raise(user_id)
        target_info = self.calculate_target(user_id)
        entries = self.water_repo.get_today(user_id)
        consumed_ml = sum([e.amount_ml for e in entries])
        target_ml = int(target_info["target_ml"])
        remaining_ml = max(target_ml - consumed_ml, 0)
        progress_percent = HydrationEngine.calculate_progress_percent(target_ml, consumed_ml)
        status = HydrationEngine.determine_status(progress_percent, settings.progress_thresholds)
        return {
            "date": date.today(),
            "target_ml": target_ml,
            "consumed_ml": int(consumed_ml),
            "remaining_ml": int(remaining_ml),
            "progress_percent": float(progress_percent),
            "status": status,
        }
