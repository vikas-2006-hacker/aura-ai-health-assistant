from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.sensor_record import SensorRecord
from app.models.wellness import NotificationPreference, NotificationRecord, RecommendationRecord
from app.repositories.user_repository import UserRepository


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
            "hydration": self._hydration_summary(records),
            "recovery": self._recovery_summary(records),
        }

    def _records_for_user(self, user_id: int):
        recent_window_start = datetime.now(timezone.utc) - timedelta(days=30)
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

    def _hydration_summary(self, records):
        hydration_ml = sum(record.value for record in records if record.data_type == "hydration")
        return {
            "current_ml": int(hydration_ml),
            "target_ml": 2500,
            "status": "on track" if hydration_ml >= 2000 else "needs attention",
        }

    def _recovery_summary(self, records):
        steps = sum(record.value for record in records if record.data_type == "steps")
        minutes = sum(record.value for record in records if record.data_type == "activity_duration") / 60.0
        if steps < 3000 and minutes < 20:
            return {"state": "moderate", "confidence": 0.65, "explanation": "Lower activity and limited exertion suggest a steady recovery level."}
        return {"state": "moderate", "confidence": 0.7, "explanation": "Recent activity and available movement data suggest a moderate recovery pattern."}

    def get_recommendations(self, user_id: int) -> dict[str, Any]:
        records = self._records_for_user(user_id)
        if not records:
            return {"items": [], "generated_at": datetime.utcnow()}

        items = []
        source_resolution = self._resolve_active_source(records)
        if source_resolution == "manual":
            return {"items": [], "generated_at": datetime.utcnow()}

        total_steps = sum(record.value for record in records if record.data_type == "steps")
        if total_steps <= 1500:
            items.append(self._build_recommendation(
                user_id,
                category="activity",
                title="Short walk suggestion",
                message="Your activity is lower than your usual level today. A short walk could help you stay active.",
                reason="Recent step totals are below the day’s expected range for this user.",
                priority=2,
                confidence=0.8,
                source_metrics=["steps"],
            ))

        if total_steps >= 10000:
            items.append(self._build_recommendation(
                user_id,
                category="hydration",
                title="Hydration reminder",
                message="Your activity is higher than usual today. Consider taking a hydration break.",
                reason="Movement volume is elevated compared with your recent baseline in the available records.",
                priority=3,
                confidence=0.8,
                source_metrics=["steps"],
            ))

        for item in items:
            self._record_recommendation(user_id, item)

        return {"items": [self._serialize_recommendation(item) for item in items], "generated_at": datetime.utcnow()}

    def get_change_insights(self, user_id: int) -> dict[str, Any]:
        reference_time = datetime.now(timezone.utc)
        records = self._records_for_user(user_id)

        today_start = reference_time.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        def normalize_record_time(record_time: datetime) -> datetime:
            if record_time.tzinfo is None:
                return record_time.replace(tzinfo=timezone.utc)
            return record_time.astimezone(timezone.utc)

        # -----------------------------
        # Today's steps
        # -----------------------------
        # -----------------------------
        # Historical daily steps
        # -----------------------------
        historical_daily_values = {}
        current_steps = 0.0

        for record in records:
            if record.data_type != "steps":
                continue

            record_time = normalize_record_time(record.start_time)

            if today_start <= record_time <= reference_time:
                current_steps += float(record.value)
                continue

            if record_time >= today_start:
                continue

            day = record_time.date()

            historical_daily_values[day] = (
                historical_daily_values.get(day, 0.0)
                + float(record.value)
            )

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
        return self._recovery_summary(self._records_for_user(user_id))

    def get_hydration_insights(self, user_id: int) -> dict[str, Any]:
        return self._hydration_summary(self._records_for_user(user_id))

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

    def _build_recommendation(self, user_id: int, *, category: str, title: str, message: str, reason: str, priority: int, confidence: float, source_metrics: list[str]) -> dict[str, Any]:
        return {
            "id": f"{user_id}:{category}:{title.lower().replace(' ', '-')}",
            "category": category,
            "title": title,
            "message": message,
            "reason": reason,
            "priority": priority,
            "confidence": confidence,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=1),
            "source_metrics": source_metrics,
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
            "created_at": payload["created_at"],
            "expires_at": payload["expires_at"],
            "source_metrics": payload["source_metrics"],
        }
