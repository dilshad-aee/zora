"""
Step 1.12 — Full auth + RBAC test matrix.

Covers every cell in the smoke-test table:
  Guest → 401, User → 403 on admin routes, Admin → 200 on everything.
Plus playlist isolation (user A can't see user B's playlists)
and no-unguarded-endpoint verification.
"""

import os
import sys
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def app():
    """Create a fresh app with an in-memory database."""
    os.environ['ZORA_ADMIN_EMAIL'] = 'admin@test.com'
    os.environ['ZORA_ADMIN_PASSWORD'] = 'adminpass1'
    os.environ['SECRET_KEY'] = 'test-secret-key-fixed'

    # Use a temp dir for downloads so tests don't touch real files
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
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture(scope='module')
def admin_client(app):
    """Authenticated admin test client."""
    client = app.test_client()
    resp = client.post('/api/auth/login', json={
        'email': 'admin@test.com',
        'password': 'adminpass1',
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.get_json()}"
    return client


@pytest.fixture(scope='module')
def user_client(app):
    """Authenticated regular-user test client."""
    client = app.test_client()
    resp = client.post('/api/auth/signup', json={
        'name': 'Regular User',
        'email': 'user@test.com',
        'password': 'userpass1',
        'confirm_password': 'userpass1',
    })
    assert resp.status_code == 201, f"User signup failed: {resp.get_json()}"
    return client


@pytest.fixture(scope='module')
def user_b_client(app):
    """Second regular user for playlist isolation tests."""
    client = app.test_client()
    resp = client.post('/api/auth/signup', json={
        'name': 'User B',
        'email': 'userb@test.com',
        'password': 'userbpass1',
        'confirm_password': 'userbpass1',
    })
    assert resp.status_code == 201, f"User B signup failed: {resp.get_json()}"
    return client


# ===========================================================================
# 1. Auth routes (login page / signup / login / logout)
# ===========================================================================

class TestAuthRoutes:
    """Guest can see login page, signup, and login."""

    def test_index_page_public(self, guest):
        resp = guest.get('/')
        assert resp.status_code == 200

    def test_signup(self, app):
        client = app.test_client()
        resp = client.post('/api/auth/signup', json={
            'name': 'New',
            'email': 'new@test.com',
            'password': 'newpass12',
            'confirm_password': 'newpass12',
        })
        assert resp.status_code == 201

    def test_login(self, app):
        client = app.test_client()
        resp = client.post('/api/auth/login', json={
            'email': 'admin@test.com',
            'password': 'adminpass1',
        })
        assert resp.status_code == 200

    def test_logout_admin(self, app):
        client = app.test_client()
        client.post('/api/auth/login', json={
            'email': 'admin@test.com',
            'password': 'adminpass1',
        })
        resp = client.post('/api/auth/logout')
        assert resp.status_code == 200

    def test_logout_user(self, app):
        client = app.test_client()
        client.post('/api/auth/signup', json={
            'name': 'Logout Test',
            'email': 'logout@test.com',
            'password': 'logoutpass1',
            'confirm_password': 'logoutpass1',
        })
        resp = client.post('/api/auth/logout')
        assert resp.status_code == 200


# ===========================================================================
# 2. Guest → 401 on all protected endpoints
# ===========================================================================

class TestGuestBlocked:
    """Unauthenticated requests must return 401."""

    def test_browse_library(self, guest):
        assert guest.get('/api/history').status_code == 401

    def test_stream_play(self, guest):
        assert guest.get('/play/test.m4a').status_code == 401

    def test_create_playlist(self, guest):
        assert guest.post('/api/playlists', json={'name': 'x'}).status_code == 401

    def test_list_playlists(self, guest):
        assert guest.get('/api/playlists').status_code == 401

    def test_search_youtube(self, guest):
        assert guest.post('/api/search', json={'query': 'test'}).status_code == 401

    def test_download_song(self, guest):
        assert guest.post('/api/download', json={'url': 'http://x'}).status_code == 401

    def test_get_settings(self, guest):
        assert guest.get('/api/settings').status_code == 401

    def test_update_settings(self, guest):
        assert guest.post('/api/settings', json={}).status_code == 401

    def test_delete_song(self, guest):
        assert guest.post('/api/history/delete/1').status_code == 401

    def test_clear_history(self, guest):
        assert guest.post('/api/history/clear').status_code == 401

    def test_queue_list(self, guest):
        assert guest.get('/api/queue').status_code == 401

    def test_queue_add(self, guest):
        assert guest.post('/api/queue/add', json={'url': 'http://x'}).status_code == 401

    def test_queue_clear(self, guest):
        assert guest.post('/api/queue/clear').status_code == 401

    def test_serve_download(self, guest):
        assert guest.get('/downloads/test.m4a').status_code == 401

    def test_get_info(self, guest):
        assert guest.post('/api/info', json={'url': 'http://x'}).status_code == 401

    def test_auth_me(self, guest):
        assert guest.get('/api/auth/me').status_code == 401


# ===========================================================================
# 3. Regular user — allowed endpoints
# ===========================================================================

class TestUserAllowed:
    """Authenticated user can browse library, stream, manage own playlists."""

    def test_browse_library(self, user_client):
        assert user_client.get('/api/history').status_code == 200

    def test_create_playlist(self, user_client):
        resp = user_client.post('/api/playlists', json={'name': 'My Playlist'})
        assert resp.status_code == 201

    def test_list_playlists(self, user_client):
        resp = user_client.get('/api/playlists')
        assert resp.status_code == 200

    def test_auth_me(self, user_client):
        resp = user_client.get('/api/auth/me')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['role'] == 'user'


# ===========================================================================
# 4. Regular user — blocked from admin endpoints (403)
# ===========================================================================

class TestUserBlocked:
    """Regular user must get 403 on admin-only routes."""

    def test_search_youtube(self, user_client):
        resp = user_client.post('/api/search', json={'query': 'test'})
        assert resp.status_code == 403

    def test_download_song(self, user_client):
        resp = user_client.post('/api/download', json={'url': 'http://x'})
        assert resp.status_code == 403

    def test_get_settings(self, user_client):
        assert user_client.get('/api/settings').status_code == 403

    def test_update_settings(self, user_client):
        assert user_client.post('/api/settings', json={}).status_code == 403

    def test_delete_song(self, user_client):
        assert user_client.post('/api/history/delete/999').status_code == 403

    def test_clear_history(self, user_client):
        assert user_client.post('/api/history/clear').status_code == 403

    def test_queue_list(self, user_client):
        assert user_client.get('/api/queue').status_code == 403

    def test_queue_add(self, user_client):
        assert user_client.post('/api/queue/add', json={'url': 'http://x'}).status_code == 403

    def test_queue_clear(self, user_client):
        assert user_client.post('/api/queue/clear').status_code == 403

    def test_serve_download(self, user_client):
        assert user_client.get('/downloads/test.m4a').status_code == 403

    def test_get_info(self, user_client):
        assert user_client.post('/api/info', json={'url': 'http://x'}).status_code == 403

    def test_get_download_status(self, user_client):
        assert user_client.get('/api/status/fake-job').status_code == 403

    def test_list_downloads(self, user_client):
        assert user_client.get('/api/downloads').status_code == 403

    def test_playlist_download_start(self, user_client):
        resp = user_client.post('/api/playlist-download/start', json={'songs': []})
        assert resp.status_code == 403

    def test_playlist_download_status(self, user_client):
        assert user_client.get('/api/playlist-download/status/fake').status_code == 403


# ===========================================================================
# 5. Admin — full access
# ===========================================================================

class TestAdminAccess:
    """Admin can access everything."""

    def test_browse_library(self, admin_client):
        assert admin_client.get('/api/history').status_code == 200

    def test_get_settings(self, admin_client):
        assert admin_client.get('/api/settings').status_code == 200

    def test_update_settings(self, admin_client):
        resp = admin_client.post('/api/settings', json={'default_format': 'm4a'})
        assert resp.status_code == 200

    def test_clear_history(self, admin_client):
        assert admin_client.post('/api/history/clear').status_code == 200

    def test_queue_list(self, admin_client):
        assert admin_client.get('/api/queue').status_code == 200

    def test_queue_clear(self, admin_client):
        assert admin_client.post('/api/queue/clear').status_code == 200

    def test_create_playlist(self, admin_client):
        resp = admin_client.post('/api/playlists', json={'name': 'Admin Playlist'})
        assert resp.status_code == 201

    def test_list_playlists(self, admin_client):
        resp = admin_client.get('/api/playlists')
        assert resp.status_code == 200

    def test_auth_me(self, admin_client):
        resp = admin_client.get('/api/auth/me')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['role'] == 'admin'


# ===========================================================================
# 6. Playlist isolation (user A ≠ user B)
# ===========================================================================

class TestPlaylistIsolation:
    """User A cannot see or modify user B's playlists."""

    def test_user_a_cannot_see_user_b_playlists(self, user_client, user_b_client, app):
        # User B creates a playlist
        resp = user_b_client.post('/api/playlists', json={'name': 'B Secret'})
        assert resp.status_code == 201
        b_playlist_id = resp.get_json()['id']

        # User A lists playlists — should NOT see B's
        resp = user_client.get('/api/playlists')
        assert resp.status_code == 200
        ids = [p['id'] for p in resp.get_json()]
        assert b_playlist_id not in ids

    def test_user_a_cannot_access_user_b_playlist_songs(self, user_client, user_b_client, app):
        # User B creates a playlist
        resp = user_b_client.post('/api/playlists', json={'name': 'B Songs'})
        assert resp.status_code == 201
        b_playlist_id = resp.get_json()['id']

        # User A tries to read it
        resp = user_client.get(f'/api/playlists/{b_playlist_id}/songs')
        assert resp.status_code == 403

    def test_user_a_cannot_delete_user_b_playlist(self, user_client, user_b_client, app):
        resp = user_b_client.post('/api/playlists', json={'name': 'B Delete Test'})
        assert resp.status_code == 201
        b_playlist_id = resp.get_json()['id']

        resp = user_client.delete(f'/api/playlists/{b_playlist_id}')
        assert resp.status_code == 403

    def test_admin_can_access_user_playlist(self, admin_client, user_b_client, app):
        """Admin bypasses ownership check."""
        resp = user_b_client.post('/api/playlists', json={'name': 'B Admin Test'})
        assert resp.status_code == 201
        b_playlist_id = resp.get_json()['id']

        resp = admin_client.get(f'/api/playlists/{b_playlist_id}/songs')
        assert resp.status_code == 200


# ===========================================================================
# 7. Verify no endpoint is accidentally unguarded
# ===========================================================================

class TestNoUnguardedEndpoints:
    """Every non-public endpoint must reject unauthenticated requests."""

    def test_all_endpoints_guarded(self, app, guest):
        """Iterate all registered endpoints and confirm non-public ones return 401."""
        PUBLIC_ENDPOINTS = {
            'auth.signup',
            'auth.login',
            'auth.request_password_reset',
            'auth.confirm_password_reset',
            'google_auth.google_start',
            'google_auth.google_callback',
            'api.index',
            'static',
        }
        SKIP_ENDPOINTS = {'static', 'google_auth.google_start', 'google_auth.google_callback'}

        with app.app_context():
            for rule in app.url_map.iter_rules():
                ep = rule.endpoint
                if ep in PUBLIC_ENDPOINTS or ep in SKIP_ENDPOINTS:
                    continue

                # Build a dummy URL (fill path params with placeholder values)
                args = {}
                for arg in rule.arguments:
                    args[arg] = 'test_placeholder'

                try:
                    url = rule.rule
                    for arg_name, arg_val in args.items():
                        url = url.replace(f'<{arg_name}>', arg_val)
                        url = url.replace(f'<int:{arg_name}>', '1')
                        url = url.replace(f'<string:{arg_name}>', arg_val)
                except Exception:
                    continue

                # Fix int converters in the URL pattern
                import re
                url = re.sub(r'<int:(\w+)>', '1', url)
                url = re.sub(r'<(\w+)>', 'test', url)

                methods = rule.methods - {'HEAD', 'OPTIONS'}
                for method in methods:
                    resp = getattr(guest, method.lower())(
                        url,
                        json={} if method in ('POST', 'PUT', 'PATCH', 'DELETE') else None,
                    )
                    assert resp.status_code in (401, 405), (
                        f"Endpoint {ep} ({method} {url}) returned {resp.status_code} "
                        f"for unauthenticated request — expected 401"
                    )
