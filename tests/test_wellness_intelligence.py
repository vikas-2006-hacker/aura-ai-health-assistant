from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services.wellness_service import WellnessService


client = TestClient(app)


def register_and_login():
    email = f"wellness+{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
        },
    )

    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert login_response.status_code == 200

    return {
        "Authorization": (
            f"Bearer {login_response.json()['access_token']}"
        )
    }


def sensor_payload(**overrides):
    start = datetime.now(timezone.utc).replace(
        hour=8,
        minute=0,
        second=0,
        microsecond=0,
    )

    payload = {
        "source_platform": "health_connect",
        "source_type": "phone",
        "data_type": "steps",
        "value": 3200,
        "unit": "count",
        "start_time": start.isoformat(),
        "end_time": (
            start + timedelta(hours=1)
        ).isoformat(),
        "source_record_id": (
            f"source-{uuid.uuid4().hex}"
        ),
    }

    payload.update(overrides)

    return payload


def create_sensor(headers, **overrides):
    response = client.post(
        "/sensor-records",
        headers=headers,
        json=sensor_payload(**overrides),
    )

    assert response.status_code == 201

    return response


def change_record(record_id, started_at, value, source_type="phone"):
    return SimpleNamespace(
        id=record_id,
        user_id=7,
        source_platform=source_type,
        source_type=source_type,
        data_type="steps",
        value=value,
        start_time=started_at,
        end_time=started_at + timedelta(hours=1),
        source_record_id=f"change-{record_id}",
        idempotency_key=None,
        validation_status="valid",
    )


def run_change_insight(monkeypatch, historical_steps, today_steps, *, mixed_timestamps=False):
    now = datetime.now(timezone.utc)
    records = []
    for day_index, value in enumerate(historical_steps, start=1):
        started_at = (now - timedelta(days=day_index)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        if mixed_timestamps and day_index % 2:
            started_at = started_at.replace(tzinfo=None)
        records.append(change_record(day_index, started_at, value))

    current_time = now - timedelta(minutes=5)
    records.append(change_record(100, current_time, today_steps, source_type="phone"))
    service = WellnessService(object())
    monkeypatch.setattr(service, "_records_for_user", lambda _user_id: records)
    return service.get_change_insights(7)["changes"][0]


def test_what_changed_service_aggregates_utc_today_and_historical_baseline(monkeypatch):
    decrease = run_change_insight(monkeypatch, [6000] * 5, 4000, mixed_timestamps=True)
    assert decrease["direction"] == "decrease"
    assert decrease["current"] == 4000
    assert decrease["comparison"] == 6000
    assert decrease["baseline_status"] == "ready"

    increase = run_change_insight(monkeypatch, [5000] * 5, 7000)
    assert increase["direction"] == "increase"
    assert increase["current"] == 7000
    assert increase["comparison"] == 5000


def test_what_changed_service_keeps_unknown_for_insufficient_history(monkeypatch):
    change = run_change_insight(monkeypatch, [6000, 6000], 4000)
    assert change["direction"] == "unknown"
    assert change["comparison"] is None
    assert change["difference_percent"] is None
    assert change["baseline_status"] == "insufficient_data"


def test_what_changed_service_prefers_wearable_without_double_counting(monkeypatch):
    now = datetime.now(timezone.utc)
    records = [
        *(change_record(day, now - timedelta(days=day), 5000) for day in range(1, 4)),
        change_record(10, now - timedelta(minutes=5), 7000, "phone"),
        change_record(11, now - timedelta(minutes=5), 9000, "wearable"),
    ]
    service = WellnessService(object())
    monkeypatch.setattr(service, "_records_for_user", lambda _user_id: records)

    change = service.get_change_insights(7)["changes"][0]
    assert change["current"] == 9000
    assert change["comparison"] == 5000
    assert change["direction"] == "increase"


def test_source_resolution_prefers_wearable_then_phone_then_manual():
    headers = register_and_login()

    start = datetime.now(timezone.utc).replace(
        hour=8,
        minute=0,
        second=0,
        microsecond=0,
    )

    wearable = sensor_payload(
        source_type="wearable",
        source_platform="health_connect",
        value=9000,
        source_record_id="wearable-steps",
        start_time=start.isoformat(),
        end_time=(
            start + timedelta(hours=1)
        ).isoformat(),
    )

    phone = sensor_payload(
        source_type="phone",
        source_platform="health_connect",
        value=7000,
        source_record_id="phone-steps",
        start_time=start.isoformat(),
        end_time=(
            start + timedelta(hours=1)
        ).isoformat(),
    )

    manual = sensor_payload(
        source_type="manual",
        source_platform="manual",
        value=5000,
        source_record_id="manual-steps",
        start_time=start.isoformat(),
        end_time=(
            start + timedelta(hours=1)
        ).isoformat(),
    )

    for payload in [wearable, phone, manual]:
        response = client.post(
            "/sensor-records",
            headers=headers,
            json=payload,
        )

        assert response.status_code == 201

    response = client.get(
        "/insights/today",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["source_resolution"]["active_source"]
        == "wearable"
    )

    assert (
        "wearable"
        in body["source_resolution"]["available_sources"]
    )

    assert (
        "phone"
        in body["source_resolution"]["available_sources"]
    )


def test_recommendation_engine_generates_and_suppresses_duplicates():
    headers = register_and_login()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    for day in range(1, 5):
        historical_start = (now - timedelta(days=day)).replace(hour=12, minute=0, second=0)
        create_sensor(
            headers,
            value=5000,
            source_record_id=f"recommendation-baseline-{day}",
            start_time=historical_start.isoformat(),
            end_time=(historical_start + timedelta(hours=1)).isoformat(),
        )

    create_sensor(
        headers,
        source_type="phone",
        source_platform="health_connect",
        value=1200,
        source_record_id="low-activity",
        start_time=(now - timedelta(hours=1)).isoformat(),
        end_time=now.isoformat(),
    )

    first = client.get(
        "/recommendations",
        headers=headers,
    )

    assert first.status_code == 200

    body = first.json()

    assert body["items"]

    assert any(
        item["category"] == "activity"
        for item in body["items"]
    )

    second = client.get(
        "/recommendations",
        headers=headers,
    )

    assert second.status_code == 200

    assert (
        len(second.json()["items"])
        == len(body["items"])
    )


def test_notification_preferences_and_deduplication():
    headers = register_and_login()

    response = client.get(
        "/notifications/preferences",
        headers=headers,
    )

    assert response.status_code == 200

    assert (
        response.json()["notifications_enabled"]
        is True
    )

    notification_response = client.get(
        "/notifications",
        headers=headers,
    )

    assert notification_response.status_code == 200

    assert "items" in notification_response.json()


def test_notification_preferences_patch_validation_and_user_isolation():
    first_headers = register_and_login()
    second_headers = register_and_login()

    first_defaults = client.get(
        "/notifications/preferences",
        headers=first_headers,
    )
    second_defaults = client.get(
        "/notifications/preferences",
        headers=second_headers,
    )
    assert first_defaults.status_code == 200
    assert first_defaults.json()["wellness_notifications"] is True
    assert first_defaults.json()["maximum_notification_frequency"] == 3

    update = client.patch(
        "/notifications/preferences",
        headers=first_headers,
        json={
            "notifications_enabled": False,
            "hydration_notifications": False,
            "wellness_notifications": False,
            "quiet_hours": {"start": "20:30", "end": "06:30"},
            "maximum_notification_frequency": 4,
        },
    )
    assert update.status_code == 200
    assert update.json()["notifications_enabled"] is False
    assert update.json()["hydration_notifications"] is False
    assert update.json()["wellness_notifications"] is False
    assert update.json()["quiet_hours"] == {"start": "20:30", "end": "06:30"}
    assert update.json()["maximum_notification_frequency"] == 4

    invalid = client.patch(
        "/notifications/preferences",
        headers=first_headers,
        json={"notifications_enabled": "false"},
    )
    assert invalid.status_code == 422
    invalid_quiet_hours = client.patch(
        "/notifications/preferences",
        headers=first_headers,
        json={"quiet_hours": {"start": "24:00"}},
    )
    assert invalid_quiet_hours.status_code == 422

    second = client.get("/notifications/preferences", headers=second_headers)
    assert second.status_code == 200
    assert second.json()["notifications_enabled"] is True
    assert second.json()["wellness_notifications"] is True


def test_what_changed_detects_decrease_against_personal_baseline():
    headers = register_and_login()

    now = datetime.now(timezone.utc).replace(
        microsecond=0,
    )

    for index in range(1, 6):
        start = now - timedelta(days=index)

        create_sensor(
            headers,
            value=6000,
            source_record_id=(
                f"baseline-decrease-{index}"
            ),
            start_time=start.isoformat(),
            end_time=(
                start + timedelta(hours=1)
            ).isoformat(),
        )

    today_start = now - timedelta(hours=1)

    create_sensor(
        headers,
        value=4000,
        source_record_id="today-decrease",
        start_time=today_start.isoformat(),
        end_time=(
            today_start + timedelta(hours=1)
        ).isoformat(),
    )

    response = client.get(
        "/insights/changes",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["changes"]

    change = body["changes"][0]

    assert change["metric"] == "steps"
    assert change["direction"] == "decrease"
    assert change["current"] == 4000
    assert change["comparison"] == 6000
    assert change["baseline_status"] == "ready"
    assert change["difference_percent"] < 0


def test_what_changed_detects_increase_against_personal_baseline():
    headers = register_and_login()

    now = datetime.now(timezone.utc).replace(
        microsecond=0,
    )

    for index in range(1, 6):
        start = now - timedelta(days=index)

        create_sensor(
            headers,
            value=5000,
            source_record_id=(
                f"baseline-increase-{index}"
            ),
            start_time=start.isoformat(),
            end_time=(
                start + timedelta(hours=1)
            ).isoformat(),
        )

    today_start = now - timedelta(hours=1)

    create_sensor(
        headers,
        value=7000,
        source_record_id="today-increase",
        start_time=today_start.isoformat(),
        end_time=(
            today_start + timedelta(hours=1)
        ).isoformat(),
    )

    response = client.get(
        "/insights/changes",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["changes"]

    change = body["changes"][0]

    assert change["metric"] == "steps"
    assert change["direction"] == "increase"
    assert change["current"] == 7000
    assert change["comparison"] == 5000
    assert change["baseline_status"] == "ready"
    assert change["difference_percent"] > 0


def test_what_changed_handles_insufficient_baseline_history():
    headers = register_and_login()

    now = datetime.now(timezone.utc).replace(
        microsecond=0,
    )

    today_start = now - timedelta(hours=1)

    create_sensor(
        headers,
        value=4000,
        source_record_id="today-insufficient",
        start_time=today_start.isoformat(),
        end_time=(
            today_start + timedelta(hours=1)
        ).isoformat(),
    )

    response = client.get(
        "/insights/changes",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["changes"]

    change = body["changes"][0]

    assert change["metric"] == "steps"
    assert change["direction"] == "unknown"
    assert change["comparison"] is None
    assert change["difference_percent"] is None
    assert (
        change["baseline_status"]
        == "insufficient_data"
    )
