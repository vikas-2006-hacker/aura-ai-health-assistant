from __future__ import annotations

from datetime import datetime
from math import isfinite

from app.repositories.sensor_record_repository import SensorRecordRepository
from app.services.activity_intelligence_service import ActivityIntelligenceService


class ActivityFeatureService:
    FEATURE_VERSION = "v1"
    MAX_STEPS_PER_RECORD = 1_000_000
    MAX_DURATION_RECORD_SECONDS = 86_400

    def __init__(self, db) -> None:
        self.repository = SensorRecordRepository(db)

    def extract_for_user(self, user_id: int, start_time: datetime, end_time: datetime) -> dict:
        start_time = ActivityIntelligenceService._normalize_datetime(start_time)
        end_time = ActivityIntelligenceService._normalize_datetime(end_time)
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
        unique_records = ActivityIntelligenceService._deduplicate(records)
        duplicate_count = len(records) - len(unique_records)
        valid_records = []
        invalid_record_count = 0
        for record in unique_records:
            if self._is_valid_record(record, start_time, end_time):
                valid_records.append(record)
            else:
                invalid_record_count += 1

        steps_records = [record for record in valid_records if record.data_type == "steps"]
        duration_records = [record for record in valid_records if record.data_type == "activity_duration"]
        steps_total = sum(
            ActivityIntelligenceService._scaled_value(record, start_time, end_time)
            for record in steps_records
        )
        merged_intervals = self._merged_intervals(duration_records, start_time, end_time)
        active_intervals = [
            (interval_end - interval_start).total_seconds()
            for interval_start, interval_end in merged_intervals
        ]
        duration_total = sum(active_intervals)
        window_seconds = (end_time - start_time).total_seconds()
        step_rates = [
            ActivityIntelligenceService._scaled_value(record, start_time, end_time)
            / ActivityIntelligenceService._interval_seconds(record, start_time, end_time)
            * 60.0
            for record in steps_records
            if ActivityIntelligenceService._interval_seconds(record, start_time, end_time) > 0
        ]
        missing_features = []
        if not steps_records:
            missing_features.append("total_steps")
        if not duration_records:
            missing_features.append("activity_duration_seconds")

        features = {
            "window_duration_seconds": round(window_seconds, 2),
            "window_hour_of_day": round(start_time.hour + start_time.minute / 60.0 + start_time.second / 3600.0, 4),
            "window_day_of_week": start_time.isoweekday(),
            "total_steps": round(steps_total, 2),
            "activity_duration_seconds": round(duration_total, 2),
            "active_interval_count": len(active_intervals),
            "average_steps_per_minute": round((steps_total / duration_total * 60.0) if duration_total > 0 else 0.0, 2),
            "maximum_steps_per_minute": round(max(step_rates, default=0.0), 2),
            "active_to_window_ratio": round(min(duration_total / window_seconds, 1.0), 4),
            "steps_per_active_second": round((steps_total / duration_total) if duration_total > 0 else 0.0, 4),
            "activity_density": round((duration_total / window_seconds) if window_seconds > 0 else 0.0, 4),
            "mean_active_interval_seconds": round(sum(active_intervals) / len(active_intervals), 2) if active_intervals else 0.0,
            "maximum_active_interval_seconds": round(max(active_intervals, default=0.0), 2),
        }
        if valid_records:
            quality_status = "valid"
        elif invalid_record_count:
            quality_status = "invalid"
        else:
            quality_status = "insufficient_data"
        source_completeness = (int(bool(steps_records)) + int(bool(duration_records))) / 2.0
        return {
            "feature_version": self.FEATURE_VERSION,
            "window_start": start_time,
            "window_end": end_time,
            "features": features,
            "quality": {
                "status": quality_status,
                "source_completeness": round(source_completeness, 2),
                "timestamp_validity": "valid",
                "duplicate_count": duplicate_count,
                "overlap_adjustment_seconds": round(self._overlap_seconds(valid_records, start_time, end_time), 2),
                "missing_feature_count": len(missing_features),
                "missing_features": missing_features,
                "invalid_record_count": invalid_record_count,
                "valid_record_count": len(valid_records),
            },
        }

    @staticmethod
    def _is_valid_record(record, start_time: datetime, end_time: datetime) -> bool:
        if record.data_type not in {"steps", "activity_duration"}:
            return False
        record_start = ActivityIntelligenceService._normalize_datetime(record.start_time)
        record_end = ActivityIntelligenceService._normalize_datetime(record.end_time)
        if record_end <= record_start or record_start >= end_time or record_end <= start_time:
            return False
        if not isfinite(float(record.value)) or record.value < 0:
            return False
        duration_seconds = (record_end - record_start).total_seconds()
        if record.data_type == "steps":
            return float(record.value).is_integer() and record.value <= ActivityFeatureService.MAX_STEPS_PER_RECORD
        return duration_seconds <= ActivityFeatureService.MAX_DURATION_RECORD_SECONDS and record.value <= ActivityFeatureService.MAX_DURATION_RECORD_SECONDS

    @staticmethod
    def _overlap_seconds(records, start_time: datetime, end_time: datetime) -> float:
        total = 0.0
        by_type = {}
        for record in records:
            record_start = max(ActivityIntelligenceService._normalize_datetime(record.start_time), start_time)
            record_end = min(ActivityIntelligenceService._normalize_datetime(record.end_time), end_time)
            by_type.setdefault(record.data_type, []).append((record_start, record_end))
        for intervals in by_type.values():
            intervals.sort()
            for index, (start, end) in enumerate(intervals):
                for next_start, next_end in intervals[index + 1:]:
                    overlap_start = max(start, next_start)
                    overlap_end = min(end, next_end)
                    if overlap_end > overlap_start:
                        total += (overlap_end - overlap_start).total_seconds()
        return total

    @staticmethod
    def _merged_intervals(records, start_time: datetime, end_time: datetime):
        intervals = []
        for record in records:
            interval_start = max(ActivityIntelligenceService._normalize_datetime(record.start_time), start_time)
            interval_end = min(ActivityIntelligenceService._normalize_datetime(record.end_time), end_time)
            if interval_end > interval_start:
                intervals.append((interval_start, interval_end))
        intervals.sort()
        merged = []
        for interval_start, interval_end in intervals:
            if not merged or interval_start > merged[-1][1]:
                merged.append([interval_start, interval_end])
            else:
                merged[-1][1] = max(merged[-1][1], interval_end)
        return [(interval_start, interval_end) for interval_start, interval_end in merged]
