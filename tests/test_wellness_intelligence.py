from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient

from app.main import app


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

    create_sensor(
        headers,
        source_type="phone",
        source_platform="health_connect",
        value=1200,
        source_record_id="low-activity",
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

    today_start = now.replace(
        hour=8,
        minute=0,
        second=0,
        microsecond=0,
    )

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

    today_start = now.replace(
        hour=8,
        minute=0,
        second=0,
        microsecond=0,
    )

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

    today_start = now.replace(
        hour=8,
        minute=0,
        second=0,
        microsecond=0,
    )

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

