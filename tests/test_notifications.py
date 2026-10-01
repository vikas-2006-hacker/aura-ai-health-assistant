from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.user import User
from app.models.wellness import NotificationPreference, NotificationRecord
from app.schemas.notification_preferences import NotificationPreferencesUpdate
from app.services import wellness_service
from app.services.wellness_service import WellnessService


@pytest.fixture
def notification_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            User(email="notification-one@example.com", password_hash="test"),
            User(email="notification-two@example.com", password_hash="test"),
        ])
        session.flush()
        session.add_all([
            NotificationPreference(
                user_id=1,
                quiet_hours_start="00:00",
                quiet_hours_end="00:00",
                maximum_notification_frequency=3,
            ),
            NotificationPreference(
                user_id=2,
                quiet_hours_start="00:00",
                quiet_hours_end="00:00",
                maximum_notification_frequency=3,
            ),
        ])
        session.commit()
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def recommendation(user_id=1, *, category="hydration", priority=3, status="active", title="Hydration reminder"):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "id": f"{user_id}:{category}:{title.lower().replace(' ', '-')}",
        "category": category,
        "title": title,
        "message": "Consider drinking water gradually today.",
        "reason": "Hydration progress is 20% with 1600 ml remaining.",
        "priority": priority,
        "status": status,
        "dedupe_key": f"{user_id}:{category}:{title.lower().replace(' ', '-')}",
        "context": {"date_utc": now.date().isoformat(), "target_ml": 2000},
        "expires_at": now + timedelta(days=1),
    }


def test_notification_is_generated_once_from_active_recommendation(notification_db):
    service = WellnessService(notification_db)
    item = recommendation()
    service._generate_notifications_from_recommendations(1, [item])
    service._generate_notifications_from_recommendations(1, [item])

    rows = service.get_notifications(1)["items"]
    assert len(rows) == 1
    assert rows[0]["type"] == "hydration"
    assert rows[0]["recommendation_ref"] == item["dedupe_key"]
    assert rows[0]["delivery_state"] == "in_app"
    assert rows[0]["priority_label"] == "high"
    assert rows[0]["read"] is False


def test_suppressed_recommendations_do_not_create_notifications(notification_db):
    service = WellnessService(notification_db)
    service._generate_notifications_from_recommendations(
        1, [recommendation(status="suppressed")]
    )
    assert service.get_notifications(1)["items"] == []


@pytest.mark.parametrize(
    ("preference", "category"),
    [
        ("notifications_enabled", "hydration"),
        ("hydration_notifications", "hydration"),
        ("activity_notifications", "activity"),
        ("recovery_notifications", "recovery"),
        ("wellness_notifications", "wellness"),
    ],
)
def test_disabled_notification_preferences_suppress_creation(notification_db, preference, category):
    service = WellnessService(notification_db)
    settings = notification_db.query(NotificationPreference).filter_by(user_id=1).one()
    setattr(settings, preference, False)
    notification_db.commit()

    service._generate_notifications_from_recommendations(
        1, [recommendation(category=category)]
    )
    assert service.get_notifications(1)["items"] == []


def test_notification_frequency_limit_and_category_types(notification_db):
    service = WellnessService(notification_db)
    preferences = notification_db.query(NotificationPreference).filter_by(user_id=1).one()
    preferences.maximum_notification_frequency = 2
    notification_db.commit()
    candidates = [
        recommendation(category="hydration", priority=3, title="Hydration"),
        recommendation(category="recovery", priority=2, title="Recovery"),
        recommendation(category="activity", priority=1, title="Activity"),
    ]

    service._generate_notifications_from_recommendations(1, candidates)
    rows = service.get_notifications(1)["items"]
    assert len(rows) == 2
    assert {item["type"] for item in rows} == {"hydration", "recovery"}


def test_notification_user_isolation_and_unread_read_flow(notification_db):
    service = WellnessService(notification_db)
    service._generate_notifications_from_recommendations(
        1, [recommendation(category="activity", title="Activity change")]
    )
    user_one = service.get_notifications(1)["items"]
    assert len(user_one) == 1
    assert service.get_notifications(2)["items"] == []
    assert service.get_unread_notifications(1)["items"][0]["read"] is False
    assert service.mark_notification_read(2, user_one[0]["id"]) is None

    updated = service.mark_notification_read(1, user_one[0]["id"])
    assert updated["read"] is True
    assert service.get_unread_notifications(1)["items"] == []


def test_notification_recommendation_context_categories_are_supported(notification_db):
    service = WellnessService(notification_db)
    candidates = [
        recommendation(category="hydration", title="Hydration context"),
        recommendation(category="recovery", title="Recovery context"),
        recommendation(category="activity", title="What Changed"),
        recommendation(category="wellness", title="Wellness context"),
    ]
    service._generate_notifications_from_recommendations(1, candidates)
    rows = service.get_notifications(1)["items"]
    assert {item["type"] for item in rows} == {"hydration", "recovery", "activity"}


def test_quiet_hours_suppress_notifications(notification_db):
    service = WellnessService(notification_db)
    preferences = notification_db.query(NotificationPreference).filter_by(user_id=1).one()
    preferences.quiet_hours_start = "00:00"
    preferences.quiet_hours_end = "23:59"
    notification_db.commit()

    service._generate_notifications_from_recommendations(1, [recommendation()])
    assert service.get_notifications(1)["items"] == []


def test_quiet_hour_boundaries_and_overnight_window():
    service = WellnessService(object())
    assert service._is_quiet_time(datetime(2026, 10, 1, 22, 0), "22:00", "07:00")
    assert service._is_quiet_time(datetime(2026, 10, 1, 23, 59), "22:00", "07:00")
    assert service._is_quiet_time(datetime(2026, 10, 1, 6, 59), "22:00", "07:00")
    assert not service._is_quiet_time(datetime(2026, 10, 1, 7, 0), "22:00", "07:00")
    assert not service._is_quiet_time(datetime(2026, 10, 1, 12, 0), "22:00", "07:00")


def test_preferences_default_update_and_validation(notification_db):
    service = WellnessService(notification_db)
    defaults = service.get_notification_preferences(1)
    assert defaults["notifications_enabled"] is True
    assert defaults["wellness_notifications"] is True
    assert defaults["quiet_hours"] == {"start": "00:00", "end": "00:00"}

    update = NotificationPreferencesUpdate.model_validate({
        "notifications_enabled": False,
        "hydration_notifications": False,
        "activity_notifications": True,
        "recovery_notifications": False,
        "wellness_notifications": False,
        "quiet_hours": {"start": "21:30", "end": "06:45"},
        "maximum_notification_frequency": 5,
    })
    saved = service.update_notification_preferences(
        1, update.model_dump(exclude_unset=True)
    )
    assert saved["notifications_enabled"] is False
    assert saved["hydration_notifications"] is False
    assert saved["activity_notifications"] is True
    assert saved["recovery_notifications"] is False
    assert saved["wellness_notifications"] is False
    assert saved["quiet_hours"] == {"start": "21:30", "end": "06:45"}
    assert saved["maximum_notification_frequency"] == 5
    assert service.get_notification_preferences(2)["notifications_enabled"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"notifications_enabled": "false"},
        {"wellness_notifications": 1},
        {"maximum_notification_frequency": -1},
        {"maximum_notification_frequency": 11},
        {"maximum_notification_frequency": True},
        {"quiet_hours": {"start": "24:00"}},
        {"quiet_hours": {"end": "7:00"}},
        {"unexpected": True},
        {},
    ],
)
def test_invalid_preference_values_are_rejected(payload):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        NotificationPreferencesUpdate.model_validate(payload)


def test_reenabling_category_allows_future_notification_and_keeps_history(notification_db):
    service = WellnessService(notification_db)
    preferences = notification_db.query(NotificationPreference).filter_by(user_id=1).one()
    preferences.hydration_notifications = False
    notification_db.commit()
    candidate = recommendation(category="hydration")

    service._generate_notifications_from_recommendations(1, [candidate])
    assert service.get_notifications(1)["items"] == []

    preferences.hydration_notifications = True
    notification_db.commit()
    service._generate_notifications_from_recommendations(1, [candidate])
    assert len(service.get_notifications(1)["items"]) == 1

    preferences.notifications_enabled = False
    notification_db.commit()
    assert len(service.get_notifications(1)["items"]) == 1


def test_frequency_cap_updates_apply_to_future_notifications(notification_db):
    service = WellnessService(notification_db)
    preferences = notification_db.query(NotificationPreference).filter_by(user_id=1).one()
    preferences.maximum_notification_frequency = 1
    notification_db.commit()
    candidates = [
        recommendation(category="hydration", title="Hydration"),
        recommendation(category="recovery", title="Recovery", priority=2),
    ]
    service._generate_notifications_from_recommendations(1, candidates)
    assert len(service.get_notifications(1)["items"]) == 1

    preferences.maximum_notification_frequency = 2
    notification_db.commit()
    service._generate_notifications_from_recommendations(1, candidates)
    assert len(service.get_notifications(1)["items"]) == 2


def test_marking_an_already_read_notification_is_safe(notification_db):
    service = WellnessService(notification_db)
    service._generate_notifications_from_recommendations(
        1, [recommendation(category="activity", title="Activity")]
    )
    item = service.get_notifications(1)["items"][0]
    assert service.mark_notification_read(1, item["id"])["read"] is True
    assert service.mark_notification_read(1, item["id"])["read"] is True


def test_recommendation_pipeline_creates_one_notification(notification_db, monkeypatch):
    class ActivitySummary:
        def __init__(self, db):
            pass

        def summarize_for_user(self, user_id, start_time, end_time):
            return {"steps": 2000, "source_types": ["phone"]}

    class Baseline:
        def __init__(self, db):
            pass

        def get_baseline(self, user_id, metric, *, reference_time):
            return {"status": "ready", "observations": 5, "baseline_value": 5000}

    class Hydration:
        def __init__(self, db):
            pass

        def get_today(self, user_id):
            raise ValueError("profile unavailable")

    monkeypatch.setattr(wellness_service, "ActivityIntelligenceService", ActivitySummary)
    monkeypatch.setattr(wellness_service, "PersonalBaselineService", Baseline)
    monkeypatch.setattr(wellness_service, "HydrationService", Hydration)
    service = WellnessService(notification_db)
    service.get_change_insights = lambda user_id: {
        "changes": [{
            "direction": "decrease",
            "current": 2000,
            "comparison": 5000,
            "difference_percent": -60,
            "baseline_status": "ready",
        }]
    }
    service.get_recovery_insights = lambda user_id: {
        "score": None,
        "state": "unknown",
        "confidence": 0,
        "drivers": [],
    }

    service.get_recommendations(1)
    service.get_recommendations(1)

    notifications = service.get_notifications(1)["items"]
    assert len(notifications) == 1
    assert notifications[0]["type"] == "activity"
    assert "personal baseline" in notifications[0]["message"] or "movement break" in notifications[0]["title"].lower()
