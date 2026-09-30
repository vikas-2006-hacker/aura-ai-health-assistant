from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.sensor_record import SensorRecord, SensorSyncRecord


class SensorRecordRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_by_source_identity(self, user_id: int, source_platform: str, source_record_id: str) -> Optional[SensorRecord]:
        return self.db.query(SensorRecord).filter(
            SensorRecord.user_id == user_id,
            SensorRecord.source_platform == source_platform,
            SensorRecord.source_record_id == source_record_id,
        ).one_or_none()

    def find_by_idempotency_key(self, user_id: int, source_platform: str, idempotency_key: str) -> Optional[SensorRecord]:
        return self.db.query(SensorRecord).filter(
            SensorRecord.user_id == user_id,
            SensorRecord.source_platform == source_platform,
            SensorRecord.idempotency_key == idempotency_key,
        ).one_or_none()

    def create(self, user_id: int, **data) -> SensorRecord:
        record = SensorRecord(user_id=user_id, **data)
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        self.db.refresh(record)
        return record

    def list_for_user(
        self,
        user_id: int,
        *,
        data_type: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        limit: int,
        offset: int,
    ) -> tuple[list[SensorRecord], int]:
        query = self.db.query(SensorRecord).filter(SensorRecord.user_id == user_id)
        if data_type is not None:
            query = query.filter(SensorRecord.data_type == data_type)
        if start_time is not None:
            query = query.filter(SensorRecord.end_time > start_time)
        if end_time is not None:
            query = query.filter(SensorRecord.start_time < end_time)
        query = query.order_by(SensorRecord.start_time.desc(), SensorRecord.id.asc())
        return query.limit(limit).offset(offset).all(), query.count()

    def create_sync_record(self, user_id: int, source_platform: str, status: str, *, accepted: int = 0, rejected: int = 0, duplicate: int = 0) -> SensorSyncRecord:
        sync_record = SensorSyncRecord(
            user_id=user_id,
            source_platform=source_platform,
            status=status,
            accepted_count=accepted,
            rejected_count=rejected,
            duplicate_count=duplicate,
        )
        self.db.add(sync_record)
        self.db.commit()
        self.db.refresh(sync_record)
        return sync_record
