from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.sensor_record_repository import SensorRecordRepository


class ActivityIntelligenceService:
    _SOURCE_PRIORITY = {"wearable": 0, "phone": 1, "manual": 2}

    def __init__(self, db) -> None:
        self.repository = SensorRecordRepository(db)

    def summarize_for_user(self, user_id: int, start_time: datetime, end_time: datetime) -> dict:
        start_time = self._normalize_datetime(start_time)
        end_time = self._normalize_datetime(end_time)
        if end_time <= start_time:
            raise ValueError("end_time must be after start_time")

        records, _ = self.repository.list_for_user(
            user_id,
            data_type=None,
            start_time=start_time,
            end_time=end_time,
            limit=1000,
            offset=0,
        )

        unique_records = self._deduplicate(records)
        valid_records = []
        for record in unique_records:
            record_start = self._normalize_datetime(record.start_time)
            record_end = self._normalize_datetime(record.end_time)
            if record.data_type not in {"steps", "activity_duration"}:
                continue
            if record_end <= record_start:
                continue
            if record_start >= end_time or record_end <= start_time:
                continue
            valid_records.append(record)

        valid_records = self._prefer_sources(valid_records)
        steps_total = sum(self._scaled_value(record, start_time, end_time) for record in valid_records if record.data_type == "steps")
        activity_total = sum(
            self._scaled_value(record, start_time, end_time)
            for record in valid_records
            if record.data_type == "activity_duration"
        )
        intervals = [
            self._interval_seconds(record, start_time, end_time)
            for record in valid_records
        ]
        active_intervals = sum(1 for seconds in intervals if seconds > 0)
        longest_interval = max(intervals) if intervals else 0.0

        classification, classification_details = self._classify(steps_total, activity_total)
        minutes = activity_total / 60.0
        explanation = (
            f"Rule-based estimate: Based on {int(round(steps_total))} steps and {minutes:.0f} minutes of "
            f"validated activity duration during the selected period. {classification_details}"
        )
        return {
            "steps": int(round(steps_total)),
            "activity_duration_seconds": round(activity_total, 2),
            "active_intervals": active_intervals,
            "longest_active_interval_seconds": round(longest_interval, 2),
            "steps_per_minute": round((steps_total / minutes) if minutes > 0 else 0.0, 2),
            "classification": classification,
            "classification_type": "rule_based",
            "explanation": explanation,
            "confidence": None,
            "source_types": sorted(
                {record.source_type for record in valid_records},
                key=lambda source: self._SOURCE_PRIORITY[source],
            ),
            "period_start": start_time,
            "period_end": end_time,
        }

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @staticmethod
    def _deduplicate(records):
        unique = []
        seen = set()
        for record in sorted(records, key=lambda item: (ActivityIntelligenceService._normalize_datetime(item.start_time), item.id)):
            source_key = (
                record.source_platform,
                record.source_record_id
                or record.idempotency_key
                or f"{record.data_type}:{ActivityIntelligenceService._normalize_datetime(record.start_time).isoformat()}:{ActivityIntelligenceService._normalize_datetime(record.end_time).isoformat()}:{record.value}",
            )
            if source_key in seen:
                continue
            unique.append(record)
            seen.add(source_key)
        return unique

    @classmethod
    def _prefer_sources(cls, records):
        preferred_by_type = {}
        for record in records:
            rank = cls._SOURCE_PRIORITY[record.source_type]
            current = preferred_by_type.get(record.data_type)
            if current is None or rank < current:
                preferred_by_type[record.data_type] = rank
        return [
            record
            for record in records
            if cls._SOURCE_PRIORITY[record.source_type]
            == preferred_by_type[record.data_type]
        ]

    @staticmethod
    def _scaled_value(record, start_time: datetime, end_time: datetime) -> float:
        record_start = ActivityIntelligenceService._normalize_datetime(record.start_time)
        record_end = ActivityIntelligenceService._normalize_datetime(record.end_time)
        overlap_start = max(record_start, start_time)
        overlap_end = min(record_end, end_time)
        full_seconds = max((record_end - record_start).total_seconds(), 0.0)
        overlap_seconds = max((overlap_end - overlap_start).total_seconds(), 0.0)
        if full_seconds <= 0 or overlap_seconds <= 0:
            return 0.0
        return float(record.value) * (overlap_seconds / full_seconds)

    @staticmethod
    def _interval_seconds(record, start_time: datetime, end_time: datetime) -> float:
        record_start = ActivityIntelligenceService._normalize_datetime(record.start_time)
        record_end = ActivityIntelligenceService._normalize_datetime(record.end_time)
        overlap_start = max(record_start, start_time)
        overlap_end = min(record_end, end_time)
        return max((overlap_end - overlap_start).total_seconds(), 0.0)

    @staticmethod
    def _classify(steps_total: float, activity_total: float) -> tuple[str, str]:
        if steps_total == 0 and activity_total == 0:
            return "sedentary", "No validated activity was detected in this period."
        if steps_total < 3000 and activity_total < 900:
            return "sedentary", "Activity is minimal and consistent with a sedentary period."
        if steps_total < 7500 and activity_total < 1800:
            return "light", "Activity is light, with a modest step count and limited active duration."
        if steps_total < 12000 and activity_total < 3600:
            return "moderate", "Activity is moderate based on a sustained step count and active duration."
        return "high", "Activity is high based on substantial validated steps and duration."
