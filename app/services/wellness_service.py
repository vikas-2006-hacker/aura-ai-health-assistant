from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.sensor_record import SensorRecord
from app.models.wellness import NotificationPreference, NotificationRecord, RecommendationRecord
from app.repositories.user_repository import UserRepository
from app.services.activity_intelligence_service import ActivityIntelligenceService
from app.services.hydration_service import HydrationService
from app.services.personal_baseline_service import PersonalBaselineService


class WellnessService:
    _SOURCE_PRIORITY = {"wearable": 0, "phone": 1, "manual": 2}

    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_repo = UserRepository(db)

    def get_today_insights(self, user_id: int) -> dict[str, Any]:
        records = self._records_for_user(user_id)
        active_source = self._resolve_active_source(records)
        available = self._available_sources(records)
        return {
            "source_resolution": {
                "active_source": active_source,
                "available_sources": available,
                "source_status": "ready" if active_source else "insufficient_data",
                "last_synchronization_time": self._latest_timestamp(records),
                "permission_status": "granted" if active_source else "not_available",
                "data_freshness": "fresh" if active_source else "missing",
            },
            "activity": self._activity_summary(records),
            "hydration": self._hydration_summary(user_id),
            "recovery": self._recovery_summary(records),
        }

    def _records_for_user(self, user_id: int):
        # SensorRecord timestamps use naive UTC in the database. Bind a naive
        # UTC cutoff so PostgreSQL does not interpret it in the session TZ.
        recent_window_start = (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).replace(tzinfo=None)
        records = self.db.query(SensorRecord).filter(
            SensorRecord.user_id == user_id,
            SensorRecord.start_time >= recent_window_start,
        ).order_by(SensorRecord.start_time.desc(), SensorRecord.id.asc()).all()
        if records:
            return records
        return self.db.query(SensorRecord).filter(
            SensorRecord.user_id == user_id,
        ).order_by(SensorRecord.start_time.desc(), SensorRecord.id.asc()).all()

    def _resolve_active_source(self, records):
        if not records:
            return "manual"
        ranked = sorted({record.source_type for record in records}, key=lambda source: self._SOURCE_PRIORITY.get(source, 99))
        if not ranked:
            return "manual"
        return ranked[0]

    def _available_sources(self, records):
        sources = {record.source_type for record in records}
        ordered = [source for source in ["wearable", "phone", "manual"] if source in sources]
        return ordered

    def _latest_timestamp(self, records):
        if not records:
            return None
        return max(record.start_time for record in records)

    def _activity_summary(self, records):
        steps = sum(record.value for record in records if record.data_type == "steps")
        minutes = sum(record.value for record in records if record.data_type == "activity_duration") / 60.0
        if steps < 3000 and minutes < 20:
            state = "low activity"
        elif steps < 8000 and minutes < 40:
            state = "normal activity"
        elif steps < 12000 and minutes < 60:
            state = "elevated activity"
        else:
            state = "high activity"
        return {
            "state": state,
            "steps": int(steps),
            "minutes": round(minutes, 1),
            "confidence": 0.7 if records else 0.0,
            "explanation": "The system used available step and duration records to classify today’s activity level.",
        }

    def _hydration_summary(self, user_id: int):
        try:
            hydration = HydrationService(self.db).get_today(user_id)
        except ValueError as exc:
            return {
                "current_ml": None,
                "target_ml": None,
                "remaining_ml": None,
                "progress_percent": None,
                "status": "unavailable",
                "basis": None,
                "explanation": str(exc),
            }
        return {
            "current_ml": hydration["consumed_ml"],
            "target_ml": hydration["target_ml"],
            "remaining_ml": hydration["remaining_ml"],
            "progress_percent": hydration["progress_percent"],
            "status": hydration["status"],
            "basis": hydration["basis"],
            "activity_level": hydration["activity_level"],
            "activity_adjustment_percent": hydration["activity_adjustment_percent"],
            "explanation": hydration["explanation"],
        }

    def _recovery_summary(self, records):
        steps = sum(record.value for record in records if record.data_type == "steps")
        minutes = sum(record.value for record in records if record.data_type == "activity_duration") / 60.0
        if steps < 3000 and minutes < 20:
            return {"state": "moderate", "confidence": 0.65, "explanation": "Lower activity and limited exertion suggest a steady recovery level."}
        return {"state": "moderate", "confidence": 0.7, "explanation": "Recent activity and available movement data suggest a moderate recovery pattern."}

    def get_recommendations(self, user_id: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        baseline_reference = today_start.replace(tzinfo=None)
        activity = ActivityIntelligenceService(self.db).summarize_for_user(
            user_id, today_start, now
        )
        baseline = PersonalBaselineService(self.db).get_baseline(
            user_id, "steps", reference_time=baseline_reference
        )
        change = self.get_change_insights(user_id)["changes"][0]
        try:
            hydration = HydrationService(self.db).get_today(user_id)
        except ValueError:
            hydration = None
        recovery = self.get_recovery_insights(user_id)

        items = []
        source_types = activity.get("source_types", [])
        if (
            hydration is not None
            and hydration["progress_percent"] <= 60
            and hydration["remaining_ml"] >= 500
        ):
            adjustment_ml = hydration.get("activity_adjustment_ml", 0) or 0
            reason = (
                f"Today's hydration progress is {hydration['progress_percent']:.1f}% "
                f"with {hydration['remaining_ml']} ml remaining."
            )
            if adjustment_ml > 0:
                reason += (
                    f" The target includes a {adjustment_ml} ml adjustment for "
                    f"{hydration.get('activity_level')} activity."
                )
            else:
                reason += " The target is based on the available profile weight."
            items.append(self._build_recommendation(
                user_id,
                category="hydration",
                title="Hydration progress reminder",
                message="Consider drinking water gradually as you continue your day.",
                reason=reason,
                priority=3 if hydration["progress_percent"] <= 30 else 2,
                confidence=0.8,
                source_metrics=["hydration_progress", "remaining_ml"],
                metric="hydration_progress",
                current_value=hydration["progress_percent"],
                reference_value=100.0,
                confidence_state="supported_profile_and_intake",
                context={
                    "date_utc": now.date().isoformat(),
                    "target_ml": hydration["target_ml"],
                    "remaining_ml": hydration["remaining_ml"],
                    "activity_level": hydration.get("activity_level"),
                    "activity_adjustment_ml": adjustment_ml,
                },
            ))

        # What Changed supplies the current value, direction, and comparison.
        # Suppress activity rules if today's source or baseline is unavailable.
        difference = change.get("difference_percent")
        if (
            source_types
            and baseline.get("status") == "ready"
            and change.get("baseline_status") == "ready"
            and difference is not None
        ):
            rule = None
            if change["direction"] == "decrease" and difference <= -25:
                rule = (
                    "Movement break suggestion",
                    "A short walk or movement break may help you add some activity today.",
                    2 if difference <= -50 else 1,
                    f"Today's {change['current']:g} steps are {abs(difference):.1f}% below "
                    f"your personal baseline of {change['comparison']:g} steps.",
                )
            elif change["direction"] == "increase" and difference >= 50:
                rule = (
                    "Higher activity context",
                    "Your activity is well above your recent baseline; consider balancing effort with rest.",
                    1,
                    f"Today's {change['current']:g} steps are {difference:.1f}% above "
                    f"your personal baseline of {change['comparison']:g} steps.",
                )
            if rule is not None:
                title, message, priority, reason = rule
                items.append(self._build_recommendation(
                    user_id,
                    category="activity",
                    title=title,
                    message=message,
                    reason=reason,
                    priority=priority,
                    confidence=0.7,
                    source_metrics=["steps", "personal_baseline"],
                    metric="steps",
                    current_value=change["current"],
                    reference_value=change["comparison"],
                    confidence_state="today_and_baseline_available",
                    context={
                        "date_utc": now.date().isoformat(),
                        "source_types": source_types,
                        "baseline_observations": baseline.get("observations"),
                        "difference_percent": difference,
                    },
                ))

        recovery_score = recovery.get("score")
        negative_drivers = [
            driver for driver in recovery.get("drivers", [])
            if driver.get("direction") == "negative"
        ]
        if recovery_score is not None and recovery_score <= 55 and negative_drivers:
            items.append(self._build_recommendation(
                user_id,
                category="recovery",
                title="Recovery support suggestion",
                message="Consider keeping your next activity session lighter and allowing time to recover.",
                reason=recovery.get(
                    "explanation",
                    "Available recovery drivers indicate additional recovery demand.",
                ),
                priority=3 if recovery_score <= 45 else 2,
                confidence=recovery.get("confidence") or 0.5,
                source_metrics=[driver["metric"] for driver in negative_drivers],
                metric="recovery_score",
                current_value=recovery_score,
                reference_value=70,
                confidence_state="recovery_inputs_available",
                context={
                    "date_utc": now.date().isoformat(),
                    "state": recovery.get("state"),
                    "drivers": negative_drivers,
                },
            ))

        for item in items:
            self._record_recommendation(user_id, item)

        return {
            "items": [self._serialize_recommendation(item) for item in items],
            "generated_at": now.replace(tzinfo=None),
        }

    def get_change_insights(self, user_id: int) -> dict[str, Any]:
        reference_time = datetime.now(timezone.utc)
        records = self._records_for_user(user_id)
        utc_today = reference_time.date()

        def normalize_record_time(record_time: datetime) -> datetime:
            # ActivityIntelligenceService handles the project's naive-UTC
            # database convention and converts aware values to UTC.
            normalized = ActivityIntelligenceService._normalize_datetime(record_time)
            return normalized.replace(tzinfo=timezone.utc)

        # Reuse the established source identity deduplication. Resolve source
        # preference separately for each UTC day so one day's wearable feed
        # does not discard another day's phone-only history.
        unique_records = ActivityIntelligenceService._deduplicate(records)
        daily_records = {}
        for record in unique_records:
            if (
                record.data_type != "steps"
                or record.validation_status != "valid"
                or record.value is None
                or float(record.value) < 0
            ):
                continue
            record_time = normalize_record_time(record.start_time)
            if record_time > reference_time:
                continue
            daily_records.setdefault(record_time.date(), []).append(record)

        historical_daily_values = {}
        current_steps = 0.0
        for day, day_records in daily_records.items():
            resolved_records = ActivityIntelligenceService._prefer_sources(day_records)
            daily_total = sum(float(record.value) for record in resolved_records)
            if day == utc_today:
                current_steps = daily_total
            elif day < utc_today:
                historical_daily_values[day] = daily_total

        # -----------------------------
        # Not enough history
        # -----------------------------
        if len(historical_daily_values) < 3:
            return {
                "summary": (
                    "Not enough historical activity data "
                    "to determine what changed"
                ),
                "changes": [
                    {
                        "metric": "steps",
                        "direction": "unknown",
                        "current": current_steps,
                        "comparison": None,
                        "difference_percent": None,
                        "baseline_status": "insufficient_data",
                    }
                ],
            }

        # -----------------------------
        # Calculate personal baseline
        # -----------------------------
        baseline_values = list(historical_daily_values.values())

        baseline_value = sum(baseline_values) / len(baseline_values)

        if baseline_value <= 0:
            return {
                "summary": (
                    "Not enough historical activity data "
                    "to determine what changed"
                ),
                "changes": [
                    {
                        "metric": "steps",
                        "direction": "unknown",
                        "current": current_steps,
                        "comparison": None,
                        "difference_percent": None,
                        "baseline_status": "insufficient_data",
                    }
                ],
            }

        # -----------------------------
        # Compare today vs baseline
        # -----------------------------
        difference_percent = (
            (current_steps - baseline_value)
            / baseline_value
        ) * 100

        if current_steps < baseline_value:
            direction = "decrease"
            summary = (
                "Today’s activity is lower than "
                "your recent personal baseline"
            )

        elif current_steps > baseline_value:
            direction = "increase"
            summary = (
                "Today’s activity is higher than "
                "your recent personal baseline"
            )

        else:
            direction = "stable"
            summary = (
                "Today’s activity is close to "
                "your recent personal baseline"
            )

        return {
            "summary": summary,
            "changes": [
                {
                    "metric": "steps",
                    "direction": direction,
                    "current": current_steps,
                    "comparison": baseline_value,
                    "difference_percent": difference_percent,
                    "baseline_status": "ready",
                }
            ],
        }

    def get_recovery_insights(self, user_id: int) -> dict[str, Any]:
        reference_time = datetime.now(timezone.utc)
        window_start = reference_time - timedelta(days=7)
        activity = ActivityIntelligenceService(self.db).summarize_for_user(
            user_id,
            window_start,
            reference_time,
        )

        # Baseline windows and SQL DateTime columns use naive UTC in this app.
        baseline_reference = (reference_time - timedelta(days=7)).replace(tzinfo=None)
        steps_baseline = PersonalBaselineService(self.db).get_baseline(
            user_id,
            "steps",
            reference_time=baseline_reference,
        )
        duration_baseline = PersonalBaselineService(self.db).get_baseline(
            user_id,
            "activity_duration",
            reference_time=baseline_reference,
        )

        try:
            hydration = HydrationService(self.db).get_today(user_id)
        except ValueError:
            hydration = None

        baseline_ready = steps_baseline["status"] == "ready"
        step_baseline_value = steps_baseline["baseline_value"]
        duration_baseline_value = duration_baseline["baseline_value"]
        activity_available = bool(activity["source_types"])

        comparison = None
        activity_ratio = None
        if baseline_ready and step_baseline_value and step_baseline_value > 0:
            comparison = round(step_baseline_value * 7, 2)
            activity_ratio = activity["steps"] / comparison

        if activity_ratio is None:
            activity_level = activity["classification"]
        elif activity_ratio >= 1.5:
            activity_level = "high"
        elif activity_ratio >= 0.85:
            activity_level = "moderate"
        else:
            activity_level = "low"

        activity_load = {
            "level": activity_level,
            "steps": activity["steps"],
            "activity_duration_seconds": activity["activity_duration_seconds"],
            "classification": activity["classification"],
            "period_days": 7,
            "comparison_to_baseline": {
                "status": steps_baseline["status"],
                "recent_steps": activity["steps"],
                "baseline_steps": comparison,
                "ratio": round(activity_ratio, 3) if activity_ratio is not None else None,
            },
        }

        hydration_context = {
            "available": hydration is not None,
            "consumed_ml": hydration["consumed_ml"] if hydration else None,
            "target_ml": hydration["target_ml"] if hydration else None,
            "progress_percent": hydration["progress_percent"] if hydration else None,
            "status": hydration["status"] if hydration else "unavailable",
            "explanation": (
                "Hydration progress is below today's target."
                if hydration and hydration["consumed_ml"] < hydration["target_ml"]
                else "Hydration progress has reached today's target."
                if hydration
                else "No supported hydration data is available."
            ),
        }

        signals = {
            "activity": {
                "available": activity_available,
                "reason": None if activity_available else "No supported activity data is available",
            },
            "steps_baseline": {
                "available": baseline_ready,
                "reason": None if baseline_ready else "At least three historical activity days are required",
                "status": steps_baseline["status"],
                "observations": steps_baseline["observations"],
                "daily_average": step_baseline_value,
            },
            "activity_duration_baseline": {
                "available": duration_baseline["status"] == "ready",
                "reason": None if duration_baseline["status"] == "ready" else "No sufficient historical duration data is available",
                "status": duration_baseline["status"],
                "daily_average_seconds": duration_baseline_value,
            },
            "hydration": {
                "available": hydration is not None,
                "reason": None if hydration is not None else "No supported data available",
            },
        }
        for signal_name in ("sleep", "hrv", "heart_rate", "stress", "temperature"):
            signals[signal_name] = {
                "available": False,
                "reason": "No supported data available",
            }

        drivers = []
        if activity_available and activity_ratio is not None:
            if activity_ratio >= 1.2:
                direction = "negative"
                activity_explanation = "Recent activity is above your personal baseline, increasing recovery demand."
            elif activity_ratio <= 0.8:
                direction = "contextual"
                activity_explanation = "Recent activity is below your personal baseline; lower activity alone does not establish recovery."
            else:
                direction = "neutral"
                activity_explanation = "Recent activity is close to your personal baseline."
            drivers.append({
                "metric": "activity_load",
                "direction": direction,
                "value": activity["steps"],
                "comparison": comparison,
                "explanation": activity_explanation,
            })

        if hydration is not None:
            hydration_on_track = hydration["consumed_ml"] >= hydration["target_ml"]
            drivers.append({
                "metric": "hydration",
                "direction": "positive" if hydration_on_track else "negative",
                "value": hydration["consumed_ml"],
                "target": hydration["target_ml"],
                "explanation": hydration_context["explanation"],
            })

        confidence = 0.0
        if activity_available:
            confidence = 0.35
            if baseline_ready:
                confidence += 0.35
            if hydration is not None:
                confidence += 0.15
            if "wearable" in activity["source_types"]:
                confidence += 0.1
            confidence = round(min(confidence, 0.95), 2)

        score = None
        if activity_available and baseline_ready and activity_ratio is not None:
            score = 70
            if activity_ratio >= 1.5:
                score -= 25
            elif activity_ratio >= 1.2:
                score -= 15
            elif activity_ratio >= 1.05:
                score -= 8
            if hydration is not None and hydration["target_ml"] > 0:
                hydration_ratio = hydration["consumed_ml"] / hydration["target_ml"]
                if hydration_ratio < 0.6:
                    score -= 10
                elif hydration_ratio < 1.0:
                    score -= 5
            score = max(0, min(100, score))
            state = "good" if score >= 70 else "moderate" if score >= 50 else "low"
            if activity_ratio <= 0.8 and state == "good":
                state = "moderate"
            if activity_ratio >= 1.5:
                state = "low" if score < 60 else "moderate"
        else:
            state = "unknown"

        if state == "unknown":
            explanation = (
                "Recovery confidence is limited because AURA needs activity data and at least three historical activity days "
                "to compare recent load with your personal baseline."
                if not baseline_ready
                else "Recovery cannot be assessed because no supported activity data is available."
            )
            recommendations = ["AURA needs more activity history before providing a stronger recovery assessment."]
        else:
            explanation_parts = []
            if activity_ratio >= 1.2:
                explanation_parts.append("Your recent activity is above your personal baseline, which increases recovery demand.")
            elif activity_ratio <= 0.8:
                explanation_parts.append("Your recent activity is below your personal baseline; this alone does not indicate good recovery.")
            else:
                explanation_parts.append("Your recent activity is close to your personal baseline.")
            if hydration is None:
                explanation_parts.append("Hydration data is unavailable, so it was not included in the score.")
            elif hydration["consumed_ml"] < hydration["target_ml"]:
                explanation_parts.append("Hydration progress is below today's target.")
            else:
                explanation_parts.append("Hydration progress has reached today's target.")
            explanation = " ".join(explanation_parts)
            if state == "good":
                recommendations = ["Your available signals suggest a manageable activity load. Continue your planned routine."]
            elif state == "low":
                recommendations = ["Consider reducing high-intensity activity today.", "Prioritize hydration and recovery."]
            else:
                recommendations = ["Consider keeping today's activity moderate.", "Prioritize hydration and allow additional recovery time if you feel fatigued."]

        return {
            "state": state,
            "score": score,
            "confidence": confidence,
            "baseline_status": steps_baseline["status"],
            "activity_load": activity_load,
            "hydration_context": hydration_context,
            "signals": signals,
            "drivers": drivers,
            "recommendations": recommendations,
            "explanation": explanation,
        }

    def get_hydration_insights(self, user_id: int) -> dict[str, Any]:
        return self._hydration_summary(user_id)

    def get_notification_preferences(self, user_id: int) -> dict[str, Any]:
        preferences = self.db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id).one_or_none()
        if preferences is None:
            preferences = NotificationPreference(
                user_id=user_id,
                notifications_enabled=True,
                hydration_notifications=True,
                activity_notifications=True,
                recovery_notifications=True,
                quiet_hours_start="22:00",
                quiet_hours_end="07:00",
                maximum_notification_frequency=3,
            )
            self.db.add(preferences)
            self.db.commit()
            self.db.refresh(preferences)
        return {
            "notifications_enabled": preferences.notifications_enabled,
            "hydration_notifications": preferences.hydration_notifications,
            "activity_notifications": preferences.activity_notifications,
            "recovery_notifications": preferences.recovery_notifications,
            "quiet_hours": {"start": preferences.quiet_hours_start, "end": preferences.quiet_hours_end},
            "maximum_notification_frequency": preferences.maximum_notification_frequency,
        }

    def update_notification_preferences(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        preferences = self.db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id).one_or_none()
        if preferences is None:
            preferences = NotificationPreference(user_id=user_id)
            self.db.add(preferences)
        for field in [
            "notifications_enabled",
            "hydration_notifications",
            "activity_notifications",
            "recovery_notifications",
            "maximum_notification_frequency",
        ]:
            if field in payload:
                setattr(preferences, field, payload[field])
        if "quiet_hours" in payload:
            quiet_hours = payload["quiet_hours"]
            preferences.quiet_hours_start = quiet_hours.get("start", preferences.quiet_hours_start)
            preferences.quiet_hours_end = quiet_hours.get("end", preferences.quiet_hours_end)
        self.db.commit()
        self.db.refresh(preferences)
        return self.get_notification_preferences(user_id)

    def get_notifications(self, user_id: int) -> dict[str, Any]:
        records = self.db.query(NotificationRecord).filter(
            NotificationRecord.user_id == user_id,
            NotificationRecord.expires_at.is_(None) | (NotificationRecord.expires_at >= datetime.utcnow()),
        ).order_by(NotificationRecord.created_at.desc()).all()
        return {
            "items": [{
                "id": item.id,
                "category": item.category,
                "title": item.title,
                "message": item.message,
                "priority": item.priority,
                "read": item.read,
                "created_at": item.created_at,
            } for item in records],
        }

    def _build_recommendation(
        self,
        user_id: int,
        *,
        category: str,
        title: str,
        message: str,
        reason: str,
        priority: int,
        confidence: float,
        source_metrics: list[str],
        metric: str | None = None,
        current_value: float | None = None,
        reference_value: float | None = None,
        confidence_state: str = "supported",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Persist naive UTC because the existing SQL DateTime columns are
        # timezone-naive; calculation and date boundaries stay aware UTC.
        created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return {
            "id": f"{user_id}:{category}:{title.lower().replace(' ', '-')}",
            "category": category,
            "title": title,
            "message": message,
            "reason": reason,
            "priority": priority,
            "confidence": confidence,
            "priority_label": {3: "high", 2: "medium", 1: "low"}.get(priority, "low"),
            "created_at": created_at,
            "expires_at": created_at + timedelta(days=1),
            "source_metrics": source_metrics,
            "metric": metric,
            "current_value": current_value,
            "reference_value": reference_value,
            "confidence_state": confidence_state,
            "context": context or {},
            "status": "active",
            "dedupe_key": f"{user_id}:{category}:{title.lower().replace(' ', '-')}",
        }

    def _record_recommendation(self, user_id: int, payload: dict[str, Any]) -> None:
        existing = self.db.query(RecommendationRecord).filter(
            RecommendationRecord.user_id == user_id,
            RecommendationRecord.dedupe_key == payload["dedupe_key"],
        ).one_or_none()
        if existing:
            return
        record = RecommendationRecord(
            user_id=user_id,
            category=payload["category"],
            title=payload["title"],
            message=payload["message"],
            reason=payload["reason"],
            priority=payload["priority"],
            confidence=payload["confidence"],
            dedupe_key=payload["dedupe_key"],
            source_metrics=payload["source_metrics"],
            created_at=payload["created_at"],
            expires_at=payload["expires_at"],
        )
        self.db.add(record)
        self.db.commit()

    def _serialize_recommendation(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": payload["id"],
            "category": payload["category"],
            "title": payload["title"],
            "message": payload["message"],
            "reason": payload["reason"],
            "priority": payload["priority"],
            "confidence": payload["confidence"],
            "priority_label": payload["priority_label"],
            "created_at": payload["created_at"],
            "expires_at": payload["expires_at"],
            "source_metrics": payload["source_metrics"],
            "metric": payload["metric"],
            "current_value": payload["current_value"],
            "reference_value": payload["reference_value"],
            "confidence_state": payload["confidence_state"],
            "context": payload["context"],
            "status": payload["status"],
        }
