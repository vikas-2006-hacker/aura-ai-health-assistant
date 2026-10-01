from app.services import wellness_service
from app.services.wellness_service import WellnessService


class FakeActivityIntelligenceService:
    result = {}

    def __init__(self, db):
        pass

    def summarize_for_user(self, user_id, start_time, end_time):
        return dict(self.result)


class FakePersonalBaselineService:
    result = {}

    def __init__(self, db):
        pass

    def get_baseline(self, user_id, metric, *, reference_time):
        return dict(self.result)


class FakeHydrationService:
    result = None

    def __init__(self, db):
        pass

    def get_today(self, user_id):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def setup_recommendations(monkeypatch):
    FakeActivityIntelligenceService.result = {
        "steps": 2000,
        "activity_duration_seconds": 0,
        "classification": "sedentary",
        "source_types": ["wearable"],
    }
    FakePersonalBaselineService.result = {
        "status": "ready",
        "baseline_value": 5000,
        "observations": 5,
    }
    FakeHydrationService.result = {
        "target_ml": 2200,
        "consumed_ml": 400,
        "remaining_ml": 1800,
        "progress_percent": 18.18,
        "status": "low",
        "activity_level": "moderate",
        "activity_adjustment_ml": 200,
    }
    monkeypatch.setattr(
        wellness_service, "ActivityIntelligenceService", FakeActivityIntelligenceService
    )
    monkeypatch.setattr(
        wellness_service, "PersonalBaselineService", FakePersonalBaselineService
    )
    monkeypatch.setattr(wellness_service, "HydrationService", FakeHydrationService)

    service = WellnessService(object())
    service.get_change_insights = lambda user_id: {
        "changes": [{
            "metric": "steps",
            "direction": "decrease",
            "current": 2000,
            "comparison": 5000,
            "difference_percent": -60.0,
            "baseline_status": "ready",
        }]
    }
    service.get_recovery_insights = lambda user_id: {
        "state": "moderate",
        "score": 60,
        "confidence": 0.8,
        "drivers": [],
        "explanation": "Activity is close to baseline.",
    }
    persisted_keys = set()
    service._record_recommendation = lambda user_id, payload: persisted_keys.add(
        payload["dedupe_key"]
    )
    return service, persisted_keys


def test_hydration_recommendation_uses_authoritative_hydration_result(monkeypatch):
    service, _ = setup_recommendations(monkeypatch)
    result = service.get_recommendations(7)
    hydration = next(item for item in result["items"] if item["category"] == "hydration")

    assert hydration["metric"] == "hydration_progress"
    assert hydration["current_value"] == 18.18
    assert hydration["reference_value"] == 100
    assert hydration["context"]["target_ml"] == 2200
    assert hydration["context"]["activity_adjustment_ml"] == 200
    assert hydration["priority_label"] == "high"
    assert "moderate activity" in hydration["reason"]


def test_hydration_recommendation_is_suppressed_when_progress_is_on_track(monkeypatch):
    service, _ = setup_recommendations(monkeypatch)
    FakeHydrationService.result = {
        "target_ml": 2200,
        "consumed_ml": 1800,
        "remaining_ml": 400,
        "progress_percent": 81.82,
        "status": "progressing",
        "activity_level": None,
        "activity_adjustment_ml": 0,
    }
    result = service.get_recommendations(7)
    assert all(item["category"] != "hydration" for item in result["items"])


def test_activity_and_what_changed_recommendation_uses_personal_baseline(monkeypatch):
    service, _ = setup_recommendations(monkeypatch)
    result = service.get_recommendations(7)
    activity = next(item for item in result["items"] if item["category"] == "activity")

    assert activity["metric"] == "steps"
    assert activity["current_value"] == 2000
    assert activity["reference_value"] == 5000
    assert activity["context"]["source_types"] == ["wearable"]
    assert activity["context"]["baseline_observations"] == 5


def test_recovery_recommendation_uses_negative_recovery_drivers(monkeypatch):
    service, _ = setup_recommendations(monkeypatch)
    service.get_recovery_insights = lambda user_id: {
        "state": "low",
        "score": 45,
        "confidence": 0.9,
        "drivers": [
            {"metric": "activity_load", "direction": "negative"},
            {"metric": "hydration", "direction": "negative"},
        ],
        "explanation": "Activity load and hydration are reducing the recovery score.",
    }

    result = service.get_recommendations(7)
    recovery = next(item for item in result["items"] if item["category"] == "recovery")
    assert recovery["source_metrics"] == ["activity_load", "hydration"]
    assert recovery["current_value"] == 45
    assert recovery["priority_label"] == "high"
    assert "hydration" in recovery["reason"]


def test_insufficient_activity_and_profile_data_do_not_create_recommendations(monkeypatch):
    service, _ = setup_recommendations(monkeypatch)
    FakeActivityIntelligenceService.result["source_types"] = []
    FakePersonalBaselineService.result["status"] = "insufficient_data"
    FakeHydrationService.result = ValueError("profile unavailable")
    service.get_change_insights = lambda user_id: {
        "changes": [{
            "metric": "steps",
            "direction": "unknown",
            "current": 0,
            "comparison": None,
            "difference_percent": None,
            "baseline_status": "insufficient_data",
        }]
    }
    service.get_recovery_insights = lambda user_id: {
        "state": "unknown",
        "score": None,
        "confidence": 0,
        "drivers": [],
    }

    assert service.get_recommendations(7)["items"] == []


def test_recommendations_are_deterministic_user_scoped_and_deduplicated(monkeypatch):
    service, persisted_keys = setup_recommendations(monkeypatch)
    first = service.get_recommendations(7)["items"]
    second = service.get_recommendations(7)["items"]

    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert len(persisted_keys) == len(first)
    assert all(item["id"].startswith("7:") for item in first)
    assert all(item["status"] == "active" for item in first)
    assert all(item["confidence_state"] for item in first)

    other_user = service.get_recommendations(8)["items"]
    assert all(item["id"].startswith("8:") for item in other_user)
