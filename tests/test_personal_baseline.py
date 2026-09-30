from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.database.session import SessionLocal
from app.services.personal_baseline_service import PersonalBaselineService

client = TestClient(app)


def create_user_and_login():
    email = f"baseline_{uuid4().hex[:8]}@example.com"
    password = "TestPassword123!"

    register = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert register.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200

    return login.json()["access_token"]


def create_sensor_record(headers, *, data_type, value, start_time, end_time):
    payload = {
        "source_platform": "health_connect",
        "source_type": "phone",
        "data_type": data_type,
        "value": value,
        "unit": "count" if data_type == "steps" else "seconds",
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "source_record_id": f"{data_type}-{uuid4().hex}",
        "idempotency_key": uuid4().hex,
    }

    response = client.post(
        "/sensor-records",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 201


def test_personal_baseline_calculates_steps():
    token = create_user_and_login()
    headers = {"Authorization": f"Bearer {token}"}

    now = datetime.now(timezone.utc).replace(microsecond=0)

    for days_ago in range(1, 6):
        start = now - timedelta(days=days_ago)
        end = start + timedelta(hours=1)

        create_sensor_record(
            headers,
            data_type="steps",
            value=8000,
            start_time=start,
            end_time=end,
        )

    login_email = None

    # Get the user id through the authenticated API.
    # The service itself remains user-scoped.
    me = client.get("/users/me", headers=headers)

    assert me.status_code == 200

    user_id = me.json()["id"]

    db = SessionLocal()

    try:
        service = PersonalBaselineService(db)

        result = service.get_baseline(
            user_id,
            "steps",
            reference_time=now,
        )

        assert result["status"] == "ready"
        assert result["observations"] == 5
        assert result["baseline_value"] == 8000
        assert result["rolling_average"] == 8000
    finally:
        db.close()


def test_personal_baseline_requires_enough_history():
    token = create_user_and_login()
    headers = {"Authorization": f"Bearer {token}"}

    now = datetime.now(timezone.utc).replace(microsecond=0)

    create_sensor_record(
        headers,
        data_type="steps",
        value=7000,
        start_time=now - timedelta(days=1),
        end_time=now - timedelta(days=1) + timedelta(hours=1),
    )

    me = client.get("/users/me", headers=headers)
    assert me.status_code == 200

    user_id = me.json()["id"]

    db = SessionLocal()

    try:
        service = PersonalBaselineService(db)

        result = service.get_baseline(
            user_id,
            "steps",
            reference_time=now,
        )

        assert result["status"] == "insufficient_data"
        assert result["baseline_value"] is None
        assert result["rolling_average"] is None
    finally:
        db.close()


def test_personal_baseline_detects_trend():
    token = create_user_and_login()
    headers = {"Authorization": f"Bearer {token}"}

    now = datetime.now(timezone.utc).replace(microsecond=0)

    values = [8000, 7000, 6000, 5000, 4500, 4000]

    for index, value in enumerate(values, start=1):
       start = now - timedelta(days=index)
       end = start + timedelta(hours=1)

       create_sensor_record(
            headers,
            data_type="steps",
            value=value,
            start_time=start,
            end_time=end,
        )

    me = client.get("/users/me", headers=headers)
    assert me.status_code == 200

    user_id = me.json()["id"]

    db = SessionLocal()

    try:
        service = PersonalBaselineService(db)

        result = service.get_baseline(
            user_id,
            "steps",
            reference_time=now,
        )

        assert result["status"] == "ready"
        assert result["observations"] == 6
        assert result["trend"] == "increasing"
    finally:
        db.close()


def test_personal_baseline_supports_activity_duration():
    token = create_user_and_login()
    headers = {"Authorization": f"Bearer {token}"}

    now = datetime.now(timezone.utc).replace(microsecond=0)

    for days_ago in range(1, 5):
        start = now - timedelta(days=days_ago)
        end = start + timedelta(minutes=30)

        create_sensor_record(
            headers,
            data_type="activity_duration",
            value=1800,
            start_time=start,
            end_time=end,
        )

    me = client.get("/users/me", headers=headers)
    assert me.status_code == 200

    user_id = me.json()["id"]

    db = SessionLocal()

    try:
        service = PersonalBaselineService(db)

        result = service.get_baseline(
            user_id,
            "activity_duration",
            reference_time=now,
        )

        assert result["status"] == "ready"
        assert result["observations"] == 4
        assert result["baseline_value"] == 1800
    finally:
        db.close()


def test_personal_baseline_rejects_unsupported_metric():
    token = create_user_and_login()

    me = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me.status_code == 200

    user_id = me.json()["id"]

    db = SessionLocal()

    try:
        service = PersonalBaselineService(db)

        try:
            service.get_baseline(user_id, "heart_rate")
            assert False, "Expected unsupported metric error"
        except ValueError as exc:
            assert "Unsupported baseline metric" in str(exc)
    finally:
        db.close()
