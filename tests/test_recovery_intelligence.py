from datetime import timezone

import pytest

from app.services import wellness_service
from app.services.wellness_service import WellnessService


class FakeActivityIntelligenceService:
    result = {}

    def __init__(self, db):
        pass

    def summarize_for_user(self, user_id, start_time, end_time):
        assert start_time.tzinfo is not None
        assert end_time.tzinfo == timezone.utc
        return dict(self.result)


class FakePersonalBaselineService:
    result = {}

    def __init__(self, db):
        pass

    def get_baseline(self, user_id, metric, *, reference_time):
        assert reference_time.tzinfo is None
        return dict(self.result[metric])


class FakeHydrationService:
    result = None

    def __init__(self, db):
        pass

    def get_today(self, user_id):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def recovery(monkeypatch):
    FakeActivityIntelligenceService.result = {
        "steps": 7000,
        "activity_duration_seconds": 1800,
        "classification": "moderate",
        "source_types": ["phone"],
    }
    FakePersonalBaselineService.result = {
        "steps": {
            "status": "ready",
            "baseline_value": 1000,
            "observations": 5,
        },
        "activity_duration": {
            "status": "ready",
            "baseline_value": 1800,
            "observations": 5,
        },
    }
    FakeHydrationService.result = {
        "consumed_ml": 2200,
        "target_ml": 2200,
        "progress_percent": 100.0,
        "status": "goal_reached",
    }
    monkeypatch.setattr(wellness_service, "ActivityIntelligenceService", FakeActivityIntelligenceService)
    monkeypatch.setattr(wellness_service, "PersonalBaselineService", FakePersonalBaselineService)
    monkeypatch.setattr(wellness_service, "HydrationService", FakeHydrationService)
    return WellnessService(object()).get_recovery_insights(7)


def test_recovery_normal_activity_and_sufficient_baseline_is_good(recovery):
    assert recovery["state"] == "good"
    assert recovery["score"] == 70
    assert recovery["baseline_status"] == "ready"


def test_recovery_activity_substantially_above_baseline_is_low(recovery):
    FakeActivityIntelligenceService.result["steps"] = 12000
    result = WellnessService(object()).get_recovery_insights(7)
    assert result["state"] == "low"
    assert result["score"] == 45


def test_recovery_activity_below_baseline_is_not_automatically_good(recovery):
    FakeActivityIntelligenceService.result["steps"] = 4000
    result = WellnessService(object()).get_recovery_insights(7)
    assert result["state"] == "moderate"
    assert result["score"] == 70


def test_recovery_hydration_below_target_reduces_score(recovery):
    FakeHydrationService.result = {
        "consumed_ml": 1000,
        "target_ml": 2200,
        "progress_percent": 45.45,
        "status": "low",
    }
    result = WellnessService(object()).get_recovery_insights(7)
    assert result["score"] == 60
    assert "below today's target" in result["hydration_context"]["explanation"]


def test_recovery_hydration_on_track_is_contextual(recovery):
    assert recovery["hydration_context"]["status"] == "goal_reached"
    assert recovery["score"] == 70


def test_recovery_insufficient_baseline_has_no_score(recovery):
    FakePersonalBaselineService.result["steps"].update(
        status="insufficient_data",
        baseline_value=None,
        observations=2,
    )
    result = WellnessService(object()).get_recovery_insights(7)
    assert result["state"] == "unknown"
    assert result["score"] is None
    assert result["baseline_status"] == "insufficient_data"
    assert "at least three historical activity days" in result["explanation"]
    assert "three historical activity days" in result["signals"]["steps_baseline"]["reason"]


def test_recovery_with_no_sensor_data_is_unknown(recovery):
    FakeActivityIntelligenceService.result.update(steps=0, activity_duration_seconds=0, source_types=[])
    result = WellnessService(object()).get_recovery_insights(7)
    assert result["state"] == "unknown"
    assert result["score"] is None
    assert result["signals"]["activity"]["available"] is False


def test_recovery_reports_supported_source_resolution(recovery):
    FakeActivityIntelligenceService.result["source_types"] = ["wearable"]
    result = WellnessService(object()).get_recovery_insights(7)
    assert result["confidence"] == 0.95


def test_recovery_uses_phone_when_phone_is_resolved(recovery):
    FakeActivityIntelligenceService.result["source_types"] = ["phone"]
    result = WellnessService(object()).get_recovery_insights(7)
    assert result["activity_load"]["steps"] == 7000
    assert result["confidence"] == 0.85


def test_recovery_accepts_manual_fallback(recovery):
    FakeActivityIntelligenceService.result["source_types"] = ["manual"]
    result = WellnessService(object()).get_recovery_insights(7)
    assert result["signals"]["activity"]["available"] is True
    assert result["confidence"] == 0.85


def test_recovery_explanation_names_actual_available_drivers(recovery):
    assert "close to your personal baseline" in recovery["explanation"]
    assert "Hydration progress has reached today's target." in recovery["hydration_context"]["explanation"]
    assert {driver["metric"] for driver in recovery["drivers"]} == {"activity_load", "hydration"}


def test_recovery_confidence_changes_with_signal_availability(recovery):
    with_hydration = recovery["confidence"]
    FakeHydrationService.result = ValueError("profile unavailable")
    without_hydration = WellnessService(object()).get_recovery_insights(7)
    assert without_hydration["confidence"] < with_hydration


def test_recovery_marks_unsupported_signals_unavailable(recovery):
    for signal in ("sleep", "hrv", "heart_rate", "stress", "temperature"):
        assert recovery["signals"][signal] == {
            "available": False,
            "reason": "No supported data available",
        }


def test_recovery_response_has_endpoint_contract_fields(recovery):
    assert {
        "state",
        "score",
        "confidence",
        "baseline_status",
        "activity_load",
        "hydration_context",
        "signals",
        "drivers",
        "recommendations",
        "explanation",
    }.issubset(recovery)
    assert isinstance(recovery["recommendations"], list)


def test_recovery_endpoint_returns_valid_response(recovery):
    from types import SimpleNamespace

    from app.api.wellness import insights_recovery

    response = insights_recovery(object(), SimpleNamespace(id=7))
    assert response["state"] == recovery["state"]
    assert response["baseline_status"] == "ready"
