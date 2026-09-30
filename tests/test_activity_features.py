from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def register_and_login() -> dict[str, str]:
    email = f"features+{uuid.uuid4().hex[:8]}@example.com"
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
        "value": 1200,
        "unit": "count",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=30)).isoformat(),
        "source_record_id": f"feature-{uuid.uuid4().hex}",
    }
    payload.update(overrides)
    return payload


def get_features(headers: dict[str, str], start: str = "2026-09-12T00:00:00Z", end: str = "2026-09-13T00:00:00Z"):
    return client.get(f"/activity/features?start_time={start}&end_time={end}", headers=headers)


def test_activity_features_are_versioned_and_deterministic():
    headers = register_and_login()
    start = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    records = [
        sensor_payload(value=1200, start_time=start.isoformat(), end_time=(start + timedelta(minutes=30)).isoformat()),
        sensor_payload(
            value=1800,
            start_time=(start + timedelta(minutes=30)).isoformat(),
            end_time=(start + timedelta(minutes=60)).isoformat(),
        ),
        sensor_payload(
            data_type="activity_duration",
            value=1800,
            unit="seconds",
            start_time=start.isoformat(),
            end_time=(start + timedelta(minutes=30)).isoformat(),
            source_record_id=f"duration-{uuid.uuid4().hex}",
        ),
    ]
    for record in records:
        assert client.post("/sensor-records", headers=headers, json=record).status_code == 201

    first = get_features(headers)
    second = get_features(headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["feature_version"] == "v1"
    assert body["features"]["total_steps"] == 3000
    assert body["features"]["activity_duration_seconds"] == 1800
    assert body["features"]["active_interval_count"] == 1
    assert body["features"]["average_steps_per_minute"] == 100.0
    assert body["features"]["active_to_window_ratio"] == 0.0208
    assert body["quality"]["status"] == "valid"
    assert body["quality"]["missing_feature_count"] == 0


def test_activity_features_clip_midnight_timezone_and_report_overlap():
    headers = register_and_login()
    first_start = datetime(2026, 9, 11, 23, 30)
    records = [
        sensor_payload(
            data_type="activity_duration",
            value=7200,
            unit="seconds",
            start_time=first_start.isoformat(),
            end_time=(first_start + timedelta(hours=2)).isoformat(),
            source_record_id="midnight-duration",
        ),
        sensor_payload(
            data_type="activity_duration",
            value=1800,
            unit="seconds",
            start_time="2026-09-12T02:30:00+02:00",
            end_time="2026-09-12T03:00:00+02:00",
            source_record_id="timezone-duration",
        ),
    ]
    for record in records:
        assert client.post("/sensor-records", headers=headers, json=record).status_code == 201

    response = get_features(headers)
    assert response.status_code == 200
    body = response.json()
    assert body["features"]["activity_duration_seconds"] == 5400
    assert body["features"]["active_interval_count"] == 1
    assert body["quality"]["overlap_adjustment_seconds"] == 1800


def test_activity_features_empty_window_is_insufficient_data():
    headers = register_and_login()
    response = get_features(headers)
    assert response.status_code == 200
    body = response.json()
    assert body["quality"]["status"] == "insufficient_data"
    assert body["quality"]["missing_feature_count"] == 2
    assert body["quality"]["missing_features"] == ["total_steps", "activity_duration_seconds"]


def test_activity_features_reject_invalid_window_and_isolate_users():
    user_one = register_and_login()
    user_two = register_and_login()
    assert client.post("/sensor-records", headers=user_one, json=sensor_payload(value=5000)).status_code == 201

    invalid = get_features(user_one, "2026-09-13T00:00:00Z", "2026-09-12T00:00:00Z")
    assert invalid.status_code == 422

    isolated = get_features(user_two)
    assert isolated.status_code == 200
    assert isolated.json()["quality"]["status"] == "insufficient_data"


def test_activity_features_handle_zero_steps_without_fabricating_missing_duration():
    headers = register_and_login()
    record = sensor_payload(value=0)
    assert client.post("/sensor-records", headers=headers, json=record).status_code == 201
    response = get_features(headers)
    assert response.status_code == 200
    body = response.json()
    assert body["features"]["total_steps"] == 0
    assert body["quality"]["status"] == "valid"
    assert body["quality"]["missing_features"] == ["activity_duration_seconds"]


def test_activity_features_mark_unreasonable_records_invalid():
    headers = register_and_login()
    assert client.post("/sensor-records", headers=headers, json=sensor_payload(value=1_000_001)).status_code == 201
    response = get_features(headers)
    assert response.status_code == 200
    body = response.json()
    assert body["quality"]["status"] == "invalid"
    assert body["quality"]["invalid_record_count"] == 1
    assert body["quality"]["valid_record_count"] == 0
