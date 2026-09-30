from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.sensor_record import (
    SensorBatchCreate,
    SensorBatchItemResponse,
    SensorBatchResponse,
    SensorDataType,
    SensorIngestionResponse,
    SensorRecordCreate,
    SensorRecordListResponse,
)
from app.services.auth_service import get_current_user
from app.services.sensor_record_service import SensorRecordService

router = APIRouter(prefix="/sensor-records", tags=["sensor-records"])
_sensor_record_adapter = TypeAdapter(SensorRecordCreate)


@router.post("", response_model=SensorIngestionResponse, status_code=status.HTTP_201_CREATED)
def ingest_sensor_record(
    payload: SensorRecordCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> SensorIngestionResponse:
    record, duplicate = SensorRecordService(db).ingest(user.id, payload)
    return SensorIngestionResponse(
        status="duplicate" if duplicate else "accepted",
        record_id=record.id,
        duplicate=duplicate,
    )


@router.post("/batch", response_model=SensorBatchResponse, status_code=status.HTTP_200_OK)
def ingest_sensor_records(
    payload: SensorBatchCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> SensorBatchResponse:
    results: list[SensorBatchItemResponse] = []
    accepted = duplicate = rejected = 0
    service = SensorRecordService(db)
    for raw_record in payload.records:
        try:
            record_payload = _sensor_record_adapter.validate_python(raw_record)
            record, is_duplicate = service.ingest(user.id, record_payload)
            if is_duplicate:
                duplicate += 1
                results.append(SensorBatchItemResponse(status="duplicate", record_id=record.id))
            else:
                accepted += 1
                results.append(SensorBatchItemResponse(status="accepted", record_id=record.id))
        except ValidationError as exc:
            rejected += 1
            results.append(
                SensorBatchItemResponse(
                    status="rejected",
                    errors=[error.get("msg", "Invalid sensor record") for error in exc.errors()],
                )
            )
    total = len(results)
    sync_status = "complete" if rejected == 0 else ("failed" if accepted == duplicate == 0 else "partial")
    return SensorBatchResponse(
        accepted_count=accepted,
        duplicate_count=duplicate,
        rejected_count=rejected,
        records=results,
        synchronization_status=sync_status,
    )


@router.get("", response_model=SensorRecordListResponse)
def list_sensor_records(
    data_type: Optional[SensorDataType] = None,
    start_time: Optional[datetime] = Query(default=None),
    end_time: Optional[datetime] = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> SensorRecordListResponse:
    data = SensorRecordService(db).list_for_user(
        user.id,
        data_type=data_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    return SensorRecordListResponse(**data)
