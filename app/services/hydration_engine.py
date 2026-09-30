from __future__ import annotations

from typing import Optional


class HydrationEngine:
    """Pure, deterministic hydration calculation helpers.

    These functions are intentionally small and side-effect free so they
    can be unit tested easily.
    """

    @staticmethod
    def calculate_base_target_ml(weight_kg: float, water_ml_per_kg: float) -> int:
        if weight_kg is None:
            raise ValueError("weight_kg is required")
        if weight_kg <= 0:
            raise ValueError("weight_kg must be positive")
        return int(round(weight_kg * water_ml_per_kg))

    @staticmethod
    def apply_activity_adjustment(target_ml: int, activity_level: Optional[str], activity_adjustments: dict) -> int:
        if activity_level is None:
            return target_ml
        adj = activity_adjustments.get(activity_level.lower()) if isinstance(activity_level, str) else None
        if adj is None:
            # unknown activity level → no adjustment
            return target_ml
        return int(round(target_ml * (1.0 + float(adj))))

    @staticmethod
    def calculate_progress_percent(target_ml: int, consumed_ml: int) -> float:
        if target_ml <= 0:
            return 0.0
        return min(100.0, round((consumed_ml / float(target_ml)) * 100.0, 2))

    @staticmethod
    def determine_status(progress_percent: float, thresholds: dict) -> str:
        # thresholds expected: {"low": 30, "needs_attention": 60, "progressing": 100}
        low = float(thresholds.get("low", 30))
        needs = float(thresholds.get("needs_attention", 60))
        progressing = float(thresholds.get("progressing", 100))
        if progress_percent < low:
            return "low"
        if progress_percent < needs:
            return "needs_attention"
        if progress_percent < progressing:
            return "progressing"
        return "goal_reached"
