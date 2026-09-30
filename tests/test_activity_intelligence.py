from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def register_and_login() -> dict[str, str]:
    email = f"activity+{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    assert client.post("/auth/register", json={"email": email, "password": password}).status_code == 201
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def sensor_payload(**overrides) -> dict:
    start = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    payload = {
        "source_platform": "health_connect",
        "source_type": "phone",
        "data_type": "steps",
        "value": 800,
        "unit": "count",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=1)).isoformat(),
        "source_record_id": f"source-{uuid.uuid4().hex}",
    }
    payload.update(overrides)
    return payload


def test_activity_summary_classifies_and_explains_rule_based_intensity():
    headers = register_and_login()
    start = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    records = [
        sensor_payload(value=4200, start_time=start.isoformat(), end_time=(start + timedelta(hours=1)).isoformat()),
        sensor_payload(value=4800, start_time=(start + timedelta(hours=1)).isoformat(), end_time=(start + timedelta(hours=2)).isoformat()),
        sensor_payload(
            data_type="activity_duration",
            value=1800,
            unit="seconds",
            start_time=(start + timedelta(minutes=30)).isoformat(),
            end_time=(start + timedelta(minutes=60)).isoformat(),
            source_record_id=f"activity-{uuid.uuid4().hex}",
        ),
    ]
    for record in records:
        response = client.post("/sensor-records", headers=headers, json=record)
        assert response.status_code == 201, response.text

    response = client.get(
        "/activity/summary?start_time=2026-09-12T00:00:00Z&end_time=2026-09-13T00:00:00Z",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["steps"] == 9000
    assert body["activity_duration_seconds"] == 1800
    assert body["classification"] == "moderate"
    assert body["classification_type"] == "rule_based"
    assert "Rule-based estimate" in body["explanation"]
    assert body["confidence"] is None


def test_activity_summary_handles_duplicates_overlap_and_midnight_boundaries():
    headers = register_and_login()
    day_start = datetime(2026, 9, 11, 23, 30)
    crossing = sensor_payload(
        data_type="activity_duration",
        value=7200,
        unit="seconds",
        start_time=day_start.isoformat(),
        end_time=(day_start + timedelta(hours=2)).isoformat(),
        source_record_id="crossing-one",
    )
    duplicate = dict(crossing)
    duplicate["source_record_id"] = "crossing-one"
    duplicate["idempotency_key"] = "retried-crossing"
    client.post("/sensor-records", headers=headers, json=crossing)
    client.post("/sensor-records", headers=headers, json=duplicate)

    response = client.get(
        "/activity/summary?start_time=2026-09-12T00:00:00Z&end_time=2026-09-12T23:59:59Z",
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["steps"] == 0
    assert body["active_intervals"] == 1
    assert body["activity_duration_seconds"] == 5400
    assert body["longest_active_interval_seconds"] == 5400


def test_activity_summary_respects_user_isolation():
    user_one = register_and_login()
    user_two = register_and_login()
    payload = sensor_payload(value=5000, source_record_id="isolation-steps")
    assert client.post("/sensor-records", headers=user_one, json=payload).status_code == 201
    response = client.get(
        "/activity/summary?start_time=2026-09-12T00:00:00Z&end_time=2026-09-13T00:00:00Z",
        headers=user_two,
    )
    assert response.status_code == 200
    assert response.json()["steps"] == 0


def test_activity_summary_prefers_wearable_over_phone_and_manual():
    headers = register_and_login()
    start = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    records = [
        sensor_payload(
            value=9000,
            source_type="wearable",
            source_record_id="wearable-steps",
            start_time=start.isoformat(),
            end_time=(start + timedelta(hours=1)).isoformat(),
        ),
        sensor_payload(
            value=7000,
            source_type="phone",
            source_record_id="phone-steps",
            start_time=start.isoformat(),
            end_time=(start + timedelta(hours=1)).isoformat(),
        ),
        sensor_payload(
            value=5000,
            source_platform="manual",
            source_type="manual",
            source_record_id="manual-steps",
            start_time=start.isoformat(),
            end_time=(start + timedelta(hours=1)).isoformat(),
        ),
    ]
    for record in records:
        assert client.post("/sensor-records", headers=headers, json=record).status_code == 201

    response = client.get(
        "/activity/summary?start_time=2026-09-12T00:00:00Z&end_time=2026-09-13T00:00:00Z",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["steps"] == 9000
    assert response.json()["source_types"] == ["wearable"]


def test_activity_summary_uses_manual_records_when_phone_data_is_absent():
    headers = register_and_login()
    start = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    manual = sensor_payload(
        source_platform="manual",
        source_type="manual",
        data_type="activity_duration",
        value=600,
        unit="seconds",
        source_record_id="manual-duration",
        start_time=start.isoformat(),
        end_time=(start + timedelta(minutes=10)).isoformat(),
    )
    assert client.post("/sensor-records", headers=headers, json=manual).status_code == 201

    response = client.get(
        "/activity/summary?start_time=2026-09-12T00:00:00Z&end_time=2026-09-13T00:00:00Z",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["activity_duration_seconds"] == 600
    assert response.json()["source_types"] == ["manual"]


def test_activity_summary_returns_valid_empty_state():
    headers = register_and_login()
    response = client.get(
        "/activity/summary?start_time=2026-09-12T00:00:00Z&end_time=2026-09-13T00:00:00Z",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["steps"] == 0
    assert response.json()["activity_duration_seconds"] == 0
    assert response.json()["classification"] == "sedentary"
    assert response.json()["source_types"] == []
