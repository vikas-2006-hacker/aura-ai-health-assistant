from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean, stdev

from app.models.sensor_record import SensorRecord
from app.services.activity_intelligence_service import ActivityIntelligenceService


class PersonalBaselineService:
    """
    Calculates deterministic personal baselines from the user's
    historical normalized sensor data.

    The baseline is intentionally user-specific and does not use
    population averages.
    """

    DEFAULT_WINDOW_DAYS = 14
    MINIMUM_OBSERVATIONS = 3

    SUPPORTED_METRICS = {
        "steps",
        "activity_duration",
    }

    def __init__(
        self,
        db,
        *,
        window_days: int = DEFAULT_WINDOW_DAYS,
        minimum_observations: int = MINIMUM_OBSERVATIONS,
    ) -> None:
        self.db = db
        self.window_days = window_days
        self.minimum_observations = minimum_observations

    def get_baseline(
        self,
        user_id: int,
        metric: str,
        *,
        reference_time: datetime | None = None,
    ) -> dict:
        if metric not in self.SUPPORTED_METRICS:
            raise ValueError(
                f"Unsupported baseline metric: {metric}"
            )

        reference_time = self._normalize_datetime(
            reference_time or datetime.now(timezone.utc)
        )

        window_start = reference_time - timedelta(
            days=self.window_days
        )

        records = (
            self.db.query(SensorRecord)
            .filter(
                SensorRecord.user_id == user_id,
                SensorRecord.data_type == metric,
                SensorRecord.start_time >= window_start,
                SensorRecord.start_time < reference_time,
            )
            .order_by(
                SensorRecord.start_time.asc(),
                SensorRecord.id.asc(),
            )
            .all()
        )

        records = self._deduplicate(records)
        records = ActivityIntelligenceService._prefer_sources(records)
        records = [
            record
            for record in records
            if self._is_valid_record(record)
        ]

        daily_values = self._aggregate_daily_values(
            records,
            window_start,
            reference_time,
        )

        observations = len(daily_values)

        if observations < self.minimum_observations:
            return {
                "metric": metric,
                "status": "insufficient_data",
                "baseline_value": None,
                "rolling_average": None,
                "variability": None,
                "trend": "unknown",
                "observations": observations,
                "window_days": self.window_days,
                "window_start": window_start,
                "window_end": reference_time,
                "calculated_at": datetime.now(timezone.utc),
            }

        values = list(daily_values.values())

        average = mean(values)

        variability = (
            stdev(values)
            if observations >= 2
            else 0.0
        )

        trend = self._calculate_trend(daily_values)

        return {
            "metric": metric,
            "status": "ready",
            "baseline_value": round(average, 2),
            "rolling_average": round(average, 2),
            "variability": round(variability, 2),
            "trend": trend,
            "observations": observations,
            "window_days": self.window_days,
            "window_start": window_start,
            "window_end": reference_time,
            "calculated_at": datetime.now(timezone.utc),
        }

    def get_all_baselines(
        self,
        user_id: int,
        *,
        reference_time: datetime | None = None,
    ) -> dict:
        return {
            metric: self.get_baseline(
                user_id,
                metric,
                reference_time=reference_time,
            )
            for metric in self.SUPPORTED_METRICS
        }

    def _aggregate_daily_values(
        self,
        records,
        window_start: datetime,
        window_end: datetime,
    ) -> dict:
        daily_totals: dict[str, float] = {}

        for record in records:
            start = max(
                self._normalize_datetime(record.start_time),
                window_start,
            )

            end = min(
                self._normalize_datetime(record.end_time),
                window_end,
            )

            if end <= start:
                continue

            day_key = start.date().isoformat()

            scaled_value = (
                ActivityIntelligenceService._scaled_value(
                    record,
                    window_start,
                    window_end,
                )
            )

            daily_totals[day_key] = (
                daily_totals.get(day_key, 0.0)
                + scaled_value
            )

        return daily_totals

    @staticmethod
    def _is_valid_record(record) -> bool:
        if record.validation_status != "valid":
            return False

        if record.value is None:
            return False

        if record.value < 0:
            return False

        return record.data_type in {
            "steps",
            "activity_duration",
        }

    @staticmethod
    def _deduplicate(records):
        unique = []
        seen = set()

        for record in sorted(
            records,
            key=lambda item: (
                PersonalBaselineService._normalize_datetime(
                    item.start_time
                ),
                item.id,
            ),
        ):
            source_key = (
                record.source_platform,
                record.source_record_id
                or record.idempotency_key
                or (
                    f"{record.data_type}:"
                    f"{PersonalBaselineService._normalize_datetime(record.start_time).isoformat()}:"
                    f"{PersonalBaselineService._normalize_datetime(record.end_time).isoformat()}:"
                    f"{record.value}"
                ),
            )

            if source_key in seen:
                continue

            seen.add(source_key)
            unique.append(record)

        return unique

    @staticmethod
    def _calculate_trend(daily_values: dict[str, float]) -> str:
        if len(daily_values) < 4:
            return "stable"

        values = list(daily_values.values())

        midpoint = len(values) // 2

        first_half = mean(values[:midpoint])
        second_half = mean(values[midpoint:])

        if first_half == 0:
            return "stable"

        percentage_change = (
            (second_half - first_half)
            / first_half
        ) * 100

        if percentage_change >= 10:
            return "increasing"

        if percentage_change <= -10:
            return "decreasing"

        return "stable"

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(
                tzinfo=None
            )

        return value
