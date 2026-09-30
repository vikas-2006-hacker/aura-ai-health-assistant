from fastapi.testclient import TestClient

from app.database import SessionLocal, get_db
from app.main import app


client = TestClient(app)


def test_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "app": "AURA",
        "status": "running",
        "version": "0.1.0",
    }


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_database_foundation_is_configured() -> None:
    assert SessionLocal is not None

    db_generator = get_db()
    db_session = next(db_generator)
    assert db_session is not None
    db_generator.close()
