from fastapi.testclient import TestClient
from app.main import app
import uuid
from datetime import datetime, timedelta


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


def test_create_and_get_today_and_history_and_delete():
    email, pwd = register_user()
    token = login(email, pwd)
    headers = auth_headers(token)

    # create a water intake
    r = client.post('/water', json={'amount_ml': 250, 'source': 'manual'}, headers=headers)
    assert r.status_code == 201
    wid = r.json()['id']

    # zero and negative rejected (validation returns 422 or 400)
    r0 = client.post('/water', json={'amount_ml': 0}, headers=headers)
    assert r0.status_code in (400, 422)
    rneg = client.post('/water', json={'amount_ml': -50}, headers=headers)
    assert rneg.status_code in (400, 422)

    # create another entry with explicit timestamp (yesterday)
    yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
    r2 = client.post('/water', json={'amount_ml': 500, 'consumed_at': yesterday}, headers=headers)
    assert r2.status_code == 201

    # today's total should include only today's entries
    r_today = client.get('/water/today', headers=headers)
    assert r_today.status_code == 200
    data = r_today.json()
    assert 'total_ml' in data
    assert data['total_ml'] >= 250

    # history
    r_hist = client.get('/water/history?limit=10&offset=0', headers=headers)
    assert r_hist.status_code == 200
    h = r_hist.json()
    assert 'entries' in h

    # delete first entry
    rdel = client.delete(f'/water/{wid}', headers=headers)
    assert rdel.status_code == 204


def test_user_isolation_and_unauthenticated_rejected():
    # register two users
    email1, pwd1 = register_user()
    token1 = login(email1, pwd1)
    headers1 = auth_headers(token1)

    email2, pwd2 = register_user()
    token2 = login(email2, pwd2)
    headers2 = auth_headers(token2)

    # user1 creates entry
    r = client.post('/water', json={'amount_ml': 300}, headers=headers1)
    assert r.status_code == 201
    wid = r.json()['id']

    # user2 cannot access or delete it
    rget = client.get(f'/water/history', headers=headers2)
    assert rget.status_code == 200
    entries = rget.json().get('entries', [])
    assert all(e['id'] != wid for e in entries)

    rdel = client.delete(f'/water/{wid}', headers=headers2)
    assert rdel.status_code in (404, 403)

    # unauthenticated requests rejected
    r_unauth = client.post('/water', json={'amount_ml': 100})
    assert r_unauth.status_code == 403 or r_unauth.status_code == 401
