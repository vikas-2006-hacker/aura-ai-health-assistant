from datetime import datetime, timedelta
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def register_and_login():
    email = f"health+{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    assert client.post("/auth/register", json={"email": email, "password": password}).status_code == 201
    response = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health_data_create_today_history_summary_and_validation():
    headers = register_and_login()
    steps = client.post("/health-data", headers=headers, json={"metric_type": "steps", "value": 8500, "unit": "count", "source": "mobile"})
    assert steps.status_code == 201
    assert steps.json()["source"] == "mobile"
    manual = client.post("/health-data", headers=headers, json={"metric_type": "activity", "value": 45, "unit": "minutes", "source": "manual"})
    assert manual.status_code == 201
    assert client.post("/health-data", headers=headers, json={"metric_type": "unknown", "value": 2, "unit": "count", "source": "mobile"}).status_code == 422
    assert client.post("/health-data", headers=headers, json={"metric_type": "steps", "value": 0, "unit": "count", "source": "mobile"}).status_code == 422
    yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
    assert client.post("/health-data", headers=headers, json={"metric_type": "sleep", "value": 7.5, "unit": "hours", "source": "manual", "recorded_at": yesterday}).status_code == 201
    today = client.get("/health-data/today", headers=headers)
    assert today.status_code == 200
    assert {entry["metric_type"] for entry in today.json()["entries"]} == {"steps", "activity"}
    history = client.get("/health-data/history?limit=2&offset=0", headers=headers)
    assert history.status_code == 200
    assert history.json()["total"] == 3
    summary = client.get("/health-data/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["metrics"] == {"steps": 8500.0, "activity": 45.0}


def test_health_data_is_authenticated_and_user_isolated():
    first = register_and_login()
    second = register_and_login()
    created = client.post("/health-data", headers=first, json={"metric_type": "calories", "value": 1850, "unit": "kcal", "source": "manual"})
    assert created.status_code == 201
    assert client.get("/health-data/history", headers=second).json()["entries"] == []
    assert client.get("/health-data/today").status_code in (401, 403)
