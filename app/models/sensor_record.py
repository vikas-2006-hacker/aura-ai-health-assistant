from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class SensorRecord(Base):
    """A normalized V1 activity record received from an approved health platform."""

    __tablename__ = "sensor_records"
    __table_args__ = (
        UniqueConstraint("user_id", "source_platform", "source_record_id", name="uq_sensor_records_source_identity"),
        UniqueConstraint("user_id", "source_platform", "idempotency_key", name="uq_sensor_records_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_platform: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    record_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="valid")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="sensor_records")


Index("ix_sensor_records_user_id", SensorRecord.user_id)
Index("ix_sensor_records_data_type", SensorRecord.data_type)
Index("ix_sensor_records_start_time", SensorRecord.start_time)
Index("ix_sensor_records_user_start_time", SensorRecord.user_id, SensorRecord.start_time)


class SensorSyncRecord(Base):
    """Minimal audit record for a normalized sensor ingestion attempt."""

    __tablename__ = "sensor_sync_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_platform: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="sensor_sync_records")


Index("ix_sensor_sync_records_user_id", SensorSyncRecord.user_id)
Index("ix_sensor_sync_records_created_at", SensorSyncRecord.created_at)
