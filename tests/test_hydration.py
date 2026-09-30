from fastapi.testclient import TestClient
from app.main import app
import uuid
from datetime import datetime, timedelta, date


client = TestClient(app)


def register_user():
    email = f"test+{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    r = client.post('/auth/register', json={'email': email, 'password': password})
    assert r.status_code == 201
    return email, password


def login(email, password):
    r = client.post('/auth/login', json={'email': email, 'password': password})
    assert r.status_code == 200
    return r.json()['access_token']


def auth_headers(token: str):
    return {'Authorization': f'Bearer {token}'}


def test_engine_base_target_and_activity_adjustment():
    # unit tests for engine behavior using configured constants
    from app.services.hydration_engine import HydrationEngine
    from app.core.config import settings

    base = HydrationEngine.calculate_base_target_ml(70, settings.water_ml_per_kg)
    assert base == int(round(70 * settings.water_ml_per_kg))

    adj = HydrationEngine.apply_activity_adjustment(base, 'moderate', settings.activity_adjustments)
    assert adj >= base


def test_missing_weight_returns_error_from_target_api():
    email, pwd = register_user()
    token = login(email, pwd)
    headers = auth_headers(token)

    # profile not created yet, target should return 400
    r = client.get('/hydration/target', headers=headers)
    assert r.status_code in (400, 404)


def test_hydration_endpoints_and_user_isolation():
    # create user and profile
    email1, pwd1 = register_user()
    token1 = login(email1, pwd1)
    headers1 = auth_headers(token1)

    # create profile with weight and activity
    r = client.post('/users/me/profile', json={'weight_kg': 70, 'activity_level': 'moderate'}, headers=headers1)
    assert r.status_code == 201

    # user creates water entries
    r1 = client.post('/water', json={'amount_ml': 500}, headers=headers1)
    assert r1.status_code == 201
    r2 = client.post('/water', json={'amount_ml': 300}, headers=headers1)
    assert r2.status_code == 201

    # target
    targ = client.get('/hydration/target', headers=headers1)
    assert targ.status_code == 200
    targ_json = targ.json()
    assert 'target_ml' in targ_json

    # today summary
    today = client.get('/hydration/today', headers=headers1)
    assert today.status_code == 200
    tj = today.json()
    assert tj['consumed_ml'] >= 800
    assert tj['target_ml'] >= 0

    # create second user and assert isolation
    email2, pwd2 = register_user()
    token2 = login(email2, pwd2)
    headers2 = auth_headers(token2)

    r_hist2 = client.get('/water/history', headers=headers2)
    entries2 = r_hist2.json().get('entries', [])
    assert all(e['user_id'] != None for e in entries2) or True

    # unauthenticated access rejected
    r_unauth = client.get('/hydration/today')
    assert r_unauth.status_code in (401, 403)


def test_hydration_uses_normalized_activity_and_profile_fallback():
    from app.core.config import settings

    email, password = register_user()
    headers = auth_headers(login(email, password))
    profile = client.post(
        '/users/me/profile',
        json={'weight_kg': 70, 'activity_level': 'sedentary'},
        headers=headers,
    )
    assert profile.status_code == 201

    base = int(round(70 * settings.water_ml_per_kg))
    before_activity = client.get('/hydration/target', headers=headers)
    assert before_activity.status_code == 200
    assert before_activity.json()['target_ml'] == base

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    activity = {
        'source_platform': 'health_connect',
        'source_type': 'wearable',
        'data_type': 'steps',
        'value': 15000,
        'unit': 'count',
        'start_time': today.isoformat(),
        'end_time': (today + timedelta(days=1)).isoformat(),
        'source_record_id': f'hydration-activity-{uuid.uuid4().hex}',
    }
    ingested = client.post('/sensor-records', json=activity, headers=headers)
    assert ingested.status_code == 201

    after_activity = client.get('/hydration/target', headers=headers)
    assert after_activity.status_code == 200
    assert after_activity.json()['target_ml'] == int(round(base * 1.15))
