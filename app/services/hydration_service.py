from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
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
        today = datetime.now(timezone.utc).date()
        period_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
        activity = ActivityIntelligenceService(self.db).summarize_for_user(
            user_id,
            period_start,
            period_start + timedelta(days=1),
        )
        has_activity = activity["steps"] > 0 or activity["activity_duration_seconds"] > 0
        activity_level = activity["classification"] if has_activity else None
        adjustment_fraction = (
            float(settings.activity_adjustments.get(activity_level.lower(), 0.0))
            if activity_level is not None
            else 0.0
        )
        target = HydrationEngine.apply_activity_adjustment(base, activity_level, settings.activity_adjustments)
        if activity_level is None:
            explanation = (
                f"Target is based on {weight:g} kg at {settings.water_ml_per_kg:g} ml/kg "
                f"({base} ml). No activity adjustment was applied because no supported "
                "activity data is available today."
            )
        else:
            explanation = (
                f"Target is based on {weight:g} kg at {settings.water_ml_per_kg:g} ml/kg "
                f"({base} ml), adjusted by {adjustment_fraction * 100:g}% for today's "
                f"{activity_level} activity."
            )
        return {
            "target_ml": int(target),
            "basis": "weight_based",
            "base_target_ml": base,
            "activity_level": activity_level,
            "activity_adjustment_percent": round(adjustment_fraction * 100, 2),
            "activity_adjustment_ml": int(target) - base,
            "explanation": explanation,
        }

    def get_today(self, user_id: int) -> Dict:
        target_info = self.calculate_target(user_id)
        entries = self.water_repo.get_today(user_id)
        consumed_ml = sum([e.amount_ml for e in entries])
        target_ml = int(target_info["target_ml"])
        remaining_ml = max(target_ml - consumed_ml, 0)
        progress_percent = HydrationEngine.calculate_progress_percent(target_ml, consumed_ml)
        status = HydrationEngine.determine_status(progress_percent, settings.progress_thresholds)
        return {
            "date": datetime.now(timezone.utc).date(),
            "target_ml": target_ml,
            "consumed_ml": int(consumed_ml),
            "remaining_ml": int(remaining_ml),
            "progress_percent": float(progress_percent),
            "status": status,
            "basis": target_info["basis"],
            "base_target_ml": target_info["base_target_ml"],
            "activity_level": target_info["activity_level"],
            "activity_adjustment_percent": target_info["activity_adjustment_percent"],
            "activity_adjustment_ml": target_info["activity_adjustment_ml"],
            "explanation": target_info["explanation"],
        }
