from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.sensor_record import SensorRecord
from app.repositories.sensor_record_repository import SensorRecordRepository
from app.schemas.sensor_record import SensorRecordCreate


class SensorRecordService:
    def __init__(self, db: Session) -> None:
        self.repository = SensorRecordRepository(db)

    def ingest(self, user_id: int, payload: SensorRecordCreate) -> tuple[SensorRecord, bool]:
        existing = None
        if payload.source_record_id is not None:
            existing = self.repository.find_by_source_identity(user_id, payload.source_platform, payload.source_record_id)
        elif payload.idempotency_key is not None:
            existing = self.repository.find_by_idempotency_key(user_id, payload.source_platform, payload.idempotency_key)
        if existing is not None:
            self.repository.create_sync_record(user_id, payload.source_platform, "complete", duplicate=1)
            return existing, True

        try:
            record = self.repository.create(
                user_id,
                source_platform=payload.source_platform,
                source_type=payload.source_type,
                data_type=payload.data_type,
                value=payload.value,
                unit=payload.unit,
                start_time=self._normalize_datetime(payload.start_time),
                end_time=self._normalize_datetime(payload.end_time),
                source_record_id=payload.source_record_id,
                idempotency_key=payload.idempotency_key,
                device_id=payload.device_id,
                confidence=payload.confidence,
                record_metadata=payload.metadata,
                validation_status="valid",
            )
        except IntegrityError:
            if payload.source_record_id is not None:
                record = self.repository.find_by_source_identity(user_id, payload.source_platform, payload.source_record_id)
            else:
                record = self.repository.find_by_idempotency_key(user_id, payload.source_platform, payload.idempotency_key)
            if record is None:
                raise
            self.repository.create_sync_record(user_id, payload.source_platform, "complete", duplicate=1)
            return record, True
        self.repository.create_sync_record(user_id, payload.source_platform, "complete", accepted=1)
        return record, False

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def list_for_user(
        self,
        user_id: int,
        *,
        data_type: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        limit: int,
        offset: int,
    ) -> dict:
        entries, total = self.repository.list_for_user(
            user_id,
            data_type=data_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
        return {"entries": entries, "limit": limit, "offset": offset, "total": total}
