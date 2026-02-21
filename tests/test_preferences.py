"""
Tests for user preferences API — functional cookie/session preferences.

Covers:
  - Guest cannot access preferences → 401
  - User can GET empty preferences → 200 with {}
  - User can PUT valid preferences → 200
  - Round-trip: PUT then GET returns saved values
  - Invalid keys rejected → 400
  - Invalid values rejected → 400
  - User isolation: User A ≠ User B
  - Bulk update merges, does not replace
  - Login response sets zora_prefs cookie
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def app():
    os.environ['ZORA_ADMIN_EMAIL'] = 'admin@test.com'
    os.environ['ZORA_ADMIN_PASSWORD'] = 'adminpass1'
    os.environ['SECRET_KEY'] = 'test-secret-key-prefs'

    tmp_dl = tempfile.mkdtemp()
    os.environ['DOWNLOAD_DIR'] = tmp_dl

    from config import config
    config.DATABASE_PATH = ':memory:'
    config.SQLALCHEMY_DATABASE_URI = 'sqlite://'
    config.DOWNLOAD_DIR = __import__('pathlib').Path(tmp_dl)
    config.THUMBNAILS_DIR = config.DOWNLOAD_DIR / 'thumbnails'
    config.ensure_dirs()

    from app import create_app
    application = create_app(testing=True)
    yield application


@pytest.fixture(scope='module')
def guest(app):
    return app.test_client()


@pytest.fixture(scope='module')
def admin_client(app):
    client = app.test_client()
    resp = client.post('/api/auth/login', json={
        'email': 'admin@test.com',
        'password': 'adminpass1',
    })
    assert resp.status_code == 200
    return client


@pytest.fixture(scope='module')
def user_a_client(app):
    client = app.test_client()
    resp = client.post('/api/auth/signup', json={
        'name': 'User A',
        'email': 'usera@test.com',
        'password': 'userapass1',
        'confirm_password': 'userapass1',
    })
    assert resp.status_code == 201
    return client


@pytest.fixture(scope='module')
def user_b_client(app):
    client = app.test_client()
    resp = client.post('/api/auth/signup', json={
        'name': 'User B',
        'email': 'userb@test.com',
        'password': 'userbpass1',
        'confirm_password': 'userbpass1',
    })
    assert resp.status_code == 201
    return client


# ===========================================================================
# 1. Guest blocked
# ===========================================================================

class TestGuestBlocked:
    def test_get_preferences_401(self, guest):
        assert guest.get('/api/preferences').status_code == 401

    def test_put_preferences_401(self, guest):
        assert guest.put('/api/preferences', json={'player_volume': '0.5'}).status_code == 401


# ===========================================================================
# 2. Basic CRUD
# ===========================================================================

class TestPreferencesCRUD:
    def test_get_empty(self, user_a_client):
        resp = user_a_client.get('/api/preferences')
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_put_valid(self, user_a_client):
        resp = user_a_client.put('/api/preferences', json={
            'player_volume': '0.75',
            'player_shuffle': 'true',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['player_volume'] == '0.75'
        assert data['player_shuffle'] == 'true'

    def test_round_trip(self, user_a_client):
        resp = user_a_client.get('/api/preferences')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['player_volume'] == '0.75'
        assert data['player_shuffle'] == 'true'

    def test_merge_update(self, user_a_client):
        """PUT adds new keys without deleting existing ones."""
        resp = user_a_client.put('/api/preferences', json={
            'library_view_mode': 'list',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        # New key present
        assert data['library_view_mode'] == 'list'
        # Old keys still present
        assert data['player_volume'] == '0.75'
        assert data['player_shuffle'] == 'true'

    def test_overwrite_existing_key(self, user_a_client):
        """PUT overwrites an existing key's value."""
        resp = user_a_client.put('/api/preferences', json={
            'player_volume': '0.3',
        })
        assert resp.status_code == 200
        assert resp.get_json()['player_volume'] == '0.3'


# ===========================================================================
# 3. Validation
# ===========================================================================

class TestPreferencesValidation:
    def test_unknown_key(self, admin_client):
        resp = admin_client.put('/api/preferences', json={
            'nonexistent_key': 'value',
        })
        assert resp.status_code == 400
        assert 'Unknown preference key' in str(resp.get_json())

    def test_invalid_volume_too_high(self, admin_client):
        resp = admin_client.put('/api/preferences', json={
            'player_volume': '1.5',
        })
        assert resp.status_code == 400

    def test_invalid_shuffle_value(self, admin_client):
        resp = admin_client.put('/api/preferences', json={
            'player_shuffle': 'maybe',
        })
        assert resp.status_code == 400

    def test_invalid_repeat_value(self, admin_client):
        resp = admin_client.put('/api/preferences', json={
            'player_repeat': 'loop',
        })
        assert resp.status_code == 400

    def test_invalid_format(self, admin_client):
        resp = admin_client.put('/api/preferences', json={
            'default_format': 'exe',
        })
        assert resp.status_code == 400

    def test_empty_body(self, admin_client):
        resp = admin_client.put('/api/preferences', json={})
        assert resp.status_code == 400

    def test_valid_all_keys(self, admin_client):
        resp = admin_client.put('/api/preferences', json={
            'player_volume': '0.8',
            'player_shuffle': 'false',
            'player_repeat': 'all',
            'library_view_mode': 'grid',
            'player_haptic': 'true',
            'default_format': 'mp3',
            'default_quality': '256',
            'theme': 'dark',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 8


# ===========================================================================
# 4. User isolation
# ===========================================================================

class TestPreferencesIsolation:
    def test_user_b_does_not_see_user_a_prefs(self, user_a_client, user_b_client):
        # User A has preferences set from earlier tests
        resp_a = user_a_client.get('/api/preferences')
        assert len(resp_a.get_json()) > 0

        # User B should have empty preferences
        resp_b = user_b_client.get('/api/preferences')
        assert resp_b.status_code == 200
        assert resp_b.get_json() == {}

    def test_user_b_set_does_not_affect_user_a(self, user_a_client, user_b_client):
        user_b_client.put('/api/preferences', json={
            'player_volume': '0.1',
        })

        # User A's volume unchanged
        resp_a = user_a_client.get('/api/preferences')
        assert resp_a.get_json()['player_volume'] == '0.3'


# ===========================================================================
# 5. Login sets zora_prefs cookie
# ===========================================================================

class TestLoginCookie:
    def test_login_sets_cookie(self, app):
        """Login response should set the zora_prefs cookie with display prefs."""
        client = app.test_client()

        # Signup and set a display pref
        client.post('/api/auth/signup', json={
            'name': 'Cookie Test',
            'email': 'cookie@test.com',
            'password': 'cookiepass1',
            'confirm_password': 'cookiepass1',
        })
        client.put('/api/preferences', json={
            'library_view_mode': 'list',
        })
        client.post('/api/auth/logout')

        # Login again
        resp = client.post('/api/auth/login', json={
            'email': 'cookie@test.com',
            'password': 'cookiepass1',
        })
        assert resp.status_code == 200

        # Check zora_prefs cookie in response
        set_cookie_headers = [
            v for k, v in resp.headers if k.lower() == 'set-cookie' and 'zora_prefs' in v
        ]
        assert len(set_cookie_headers) > 0, "zora_prefs cookie not set on login"

        import json
        from urllib.parse import unquote
        # Parse cookie value from Set-Cookie header
        cookie_header = set_cookie_headers[0]
        cookie_value = cookie_header.split('zora_prefs=')[1].split(';')[0]
        cookie_value = unquote(cookie_value)
        # Flask wraps JSON in quotes, so json.loads gives a string first
        parsed = json.loads(cookie_value)
        cookie_data = json.loads(parsed) if isinstance(parsed, str) else parsed
        assert cookie_data.get('library_view_mode') == 'list'
