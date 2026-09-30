from datetime import datetime, timedelta
import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def register_and_login() -> dict[str, str]:
    email = f"sensor+{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    assert client.post("/auth/register", json={"email": email, "password": password}).status_code == 201
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def sensor_payload(**overrides) -> dict:
    start = datetime.utcnow().replace(microsecond=0)
    payload = {
        "source_platform": "health_connect",
        "source_type": "phone",
        "data_type": "steps",
        "value": 6500,
        "unit": "count",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=12)).isoformat(),
        "source_record_id": f"source-{uuid.uuid4().hex}",
    }
    payload.update(overrides)
    return payload


def test_sensor_record_validation_and_authenticated_creation():
    headers = register_and_login()
    response = client.post("/sensor-records", headers=headers, json=sensor_payload())
    assert response.status_code == 201
    assert response.json()["status"] == "accepted"
    assert response.json()["duplicate"] is False

    duration = sensor_payload(data_type="activity_duration", value=1800, unit="seconds")
    assert client.post("/sensor-records", headers=headers, json=duration).status_code == 201
    assert client.post("/sensor-records", headers=headers, json=sensor_payload(value=-1)).status_code == 422
    assert client.post("/sensor-records", headers=headers, json=sensor_payload(unit="steps")).status_code == 422
    bad_interval = sensor_payload()
    bad_interval["end_time"] = bad_interval["start_time"]
    assert client.post("/sensor-records", headers=headers, json=bad_interval).status_code == 422
    assert client.post("/sensor-records", headers=headers, json=sensor_payload(data_type="heart_rate", unit="bpm")).status_code == 422
    assert client.post("/sensor-records", headers=headers, json=sensor_payload(value=1.5)).status_code == 422
    assert client.post("/sensor-records", headers=headers, json=sensor_payload(value="Infinity")).status_code == 422

    manual = sensor_payload(
        source_platform="manual",
        source_type="manual",
        source_record_id=f"manual-{uuid.uuid4().hex}",
    )
    assert client.post("/sensor-records", headers=headers, json=manual).status_code == 201


def test_sensor_record_preserves_metadata():
    headers = register_and_login()
    response = client.post(
        "/sensor-records",
        headers=headers,
        json=sensor_payload(metadata={"aggregation": "daily", "original_unit": "count"}),
    )
    assert response.status_code == 201
    records = client.get("/sensor-records", headers=headers)
    assert records.json()["entries"][0]["metadata"] == {"aggregation": "daily", "original_unit": "count"}

    invalid = sensor_payload(metadata={"unbounded_payload": {"raw": "data"}})
    assert client.post("/sensor-records", headers=headers, json=invalid).status_code == 422


def test_sensor_record_idempotency_listing_and_user_isolation():
    first = register_and_login()
    second = register_and_login()
    payload = sensor_payload()

    created = client.post("/sensor-records", headers=first, json=payload)
    assert created.status_code == 201
    record_id = created.json()["record_id"]
    duplicate = client.post("/sensor-records", headers=first, json=payload)
    assert duplicate.status_code == 201
    assert duplicate.json() == {"status": "duplicate", "record_id": record_id, "duplicate": True}

    fallback = sensor_payload(source_record_id=None, idempotency_key=f"retry-{uuid.uuid4().hex}")
    assert client.post("/sensor-records", headers=first, json=fallback).json()["status"] == "accepted"
    assert client.post("/sensor-records", headers=first, json=fallback).json()["status"] == "duplicate"

    first_records = client.get("/sensor-records?data_type=steps", headers=first)
    assert first_records.status_code == 200
    assert first_records.json()["total"] == 2
    assert first_records.json()["entries"][0]["id"] == record_id
    assert client.get("/sensor-records", headers=second).json()["entries"] == []
    assert client.post("/sensor-records", json=payload).status_code in (401, 403)
    assert client.get("/sensor-records").status_code in (401, 403)


def test_sensor_record_time_range_filtering():
    headers = register_and_login()
    start = datetime.utcnow().replace(microsecond=0)
    first = sensor_payload(start_time=start.isoformat(), end_time=(start + timedelta(hours=1)).isoformat())
    second_start = start + timedelta(days=2)
    second = sensor_payload(start_time=second_start.isoformat(), end_time=(second_start + timedelta(hours=1)).isoformat())
    assert client.post("/sensor-records", headers=headers, json=first).status_code == 201
    assert client.post("/sensor-records", headers=headers, json=second).status_code == 201
    response = client.get(
        f"/sensor-records?start_time={(start + timedelta(days=1)).isoformat()}&end_time={(start + timedelta(days=3)).isoformat()}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_sensor_record_time_range_includes_intervals_crossing_window_boundary():
    headers = register_and_login()
    start = datetime.utcnow().replace(microsecond=0)
    crossing = sensor_payload(
        start_time=(start - timedelta(hours=1)).isoformat(),
        end_time=(start + timedelta(hours=1)).isoformat(),
    )
    assert client.post("/sensor-records", headers=headers, json=crossing).status_code == 201
    response = client.get(
        f"/sensor-records?start_time={start.isoformat()}&end_time={(start + timedelta(hours=2)).isoformat()}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_sensor_record_batch_allows_partial_validation_and_duplicates():
    headers = register_and_login()
    valid = sensor_payload()
    response = client.post("/sensor-records/batch", headers=headers, json={"records": [valid, valid, sensor_payload(value=-1)]})
    assert response.status_code == 200
    body = response.json()
    assert body["accepted_count"] == 1
    assert body["duplicate_count"] == 1
    assert body["rejected_count"] == 1
    assert body["synchronization_status"] == "partial"
