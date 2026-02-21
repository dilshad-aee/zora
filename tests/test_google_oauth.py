"""
Step 2.4 — Google OAuth smoke tests.

Tests the Google OAuth flow using mocked Google responses:
- New Google user → creates account with role=user, auth_provider=google
- Existing local account same email → links, sets auth_provider=hybrid
- Deactivated account → rejected
- Login state persists after redirect
"""

import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope='module')
def app():
    """Create app with Google OAuth configured."""
    os.environ['ZORA_ADMIN_EMAIL'] = 'admin@test.com'
    os.environ['ZORA_ADMIN_PASSWORD'] = 'adminpass1'
    os.environ['SECRET_KEY'] = 'test-secret-key-fixed'
    os.environ['GOOGLE_CLIENT_ID'] = 'fake-client-id'
    os.environ['GOOGLE_CLIENT_SECRET'] = 'fake-client-secret'

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


def _mock_google_userinfo(email, name='Test User', sub='google-sub-123', verified=True, picture=''):
    """Build a mock userinfo dict mimicking Google's response."""
    return {
        'sub': sub,
        'email': email,
        'email_verified': verified,
        'name': name,
        'picture': picture,
    }


class TestGoogleOAuthStart:
    """Test the /api/auth/google/start redirect."""

    def test_start_redirects(self, app):
        client = app.test_client()
        resp = client.get('/api/auth/google/start')
        # Should redirect to Google (302)
        assert resp.status_code == 302
        assert 'accounts.google.com' in resp.headers.get('Location', '')

    def test_start_is_public(self, app):
        """Google start must be accessible without auth (public endpoint)."""
        client = app.test_client()
        resp = client.get('/api/auth/google/start')
        assert resp.status_code != 401


class TestGoogleOAuthCallback:
    """Test the /api/auth/google/callback handling."""

    def test_new_google_user_creates_account(self, app):
        """Google login with no existing account creates new user."""
        client = app.test_client()

        userinfo = _mock_google_userinfo('newgoogle@test.com', name='Google User', sub='sub-new-1')
        token = {'userinfo': userinfo}

        with patch('app.auth.google.oauth') as mock_oauth:
            mock_google = MagicMock()
            mock_google.authorize_access_token.return_value = token
            mock_oauth.create_client.return_value = mock_google

            resp = client.get('/api/auth/google/callback')
            assert resp.status_code == 302
            assert resp.headers.get('Location', '').endswith('/')

        # Verify user is logged in
        me_resp = client.get('/api/auth/me')
        assert me_resp.status_code == 200
        data = me_resp.get_json()
        assert data['email'] == 'newgoogle@test.com'
        assert data['role'] == 'user'

        # Verify in DB
        with app.app_context():
            from app.models import User
            user = User.query.filter_by(email='newgoogle@test.com').first()
            assert user is not None
            assert user.auth_provider == 'google'
            assert user.google_sub == 'sub-new-1'
            assert user.email_verified is True

    def test_existing_local_account_links(self, app):
        """Google login with existing local account links and sets hybrid."""
        # First create a local account
        client = app.test_client()
        signup_resp = client.post('/api/auth/signup', json={
            'name': 'Local User',
            'email': 'localuser@test.com',
            'password': 'localpass1',
            'confirm_password': 'localpass1',
        })
        assert signup_resp.status_code == 201

        # Logout
        client.post('/api/auth/logout')

        # Now login via Google with the same email
        userinfo = _mock_google_userinfo('localuser@test.com', name='Local User', sub='sub-link-1')
        token = {'userinfo': userinfo}

        with patch('app.auth.google.oauth') as mock_oauth:
            mock_google = MagicMock()
            mock_google.authorize_access_token.return_value = token
            mock_oauth.create_client.return_value = mock_google

            resp = client.get('/api/auth/google/callback')
            assert resp.status_code == 302

        # Verify linked
        with app.app_context():
            from app.models import User
            user = User.query.filter_by(email='localuser@test.com').first()
            assert user.auth_provider == 'hybrid'
            assert user.google_sub == 'sub-link-1'

    def test_deactivated_account_rejected(self, app):
        """Google login with deactivated account redirects with error."""
        # Create and deactivate a user
        with app.app_context():
            from app.models import db, User
            user = User(
                name='Deactivated',
                email='deactivated@test.com',
                role='user',
                auth_provider='google',
                google_sub='sub-deactivated',
                is_active=False,
                email_verified=True,
            )
            db.session.add(user)
            db.session.commit()

        client = app.test_client()
        userinfo = _mock_google_userinfo('deactivated@test.com', sub='sub-deactivated')
        token = {'userinfo': userinfo}

        with patch('app.auth.google.oauth') as mock_oauth:
            mock_google = MagicMock()
            mock_google.authorize_access_token.return_value = token
            mock_oauth.create_client.return_value = mock_google

            resp = client.get('/api/auth/google/callback')
            assert resp.status_code == 302
            assert 'error=account_disabled' in resp.headers.get('Location', '')

        # Verify NOT logged in
        me_resp = client.get('/api/auth/me')
        assert me_resp.status_code == 401

    def test_unverified_google_email_rejected(self, app):
        """Google login with unverified email is rejected."""
        client = app.test_client()
        userinfo = _mock_google_userinfo('unverified@test.com', verified=False, sub='sub-unverified')
        token = {'userinfo': userinfo}

        with patch('app.auth.google.oauth') as mock_oauth:
            mock_google = MagicMock()
            mock_google.authorize_access_token.return_value = token
            mock_oauth.create_client.return_value = mock_google

            resp = client.get('/api/auth/google/callback')
            assert resp.status_code == 302
            assert 'error=google_email_not_verified' in resp.headers.get('Location', '')

    def test_auth_failure_redirects_with_error(self, app):
        """Failed token exchange redirects with error."""
        client = app.test_client()

        with patch('app.auth.google.oauth') as mock_oauth:
            mock_google = MagicMock()
            mock_google.authorize_access_token.side_effect = Exception('Token error')
            mock_oauth.create_client.return_value = mock_google

            resp = client.get('/api/auth/google/callback')
            assert resp.status_code == 302
            assert 'error=google_auth_failed' in resp.headers.get('Location', '')

    def test_login_state_persists(self, app):
        """After Google login, session persists across requests."""
        client = app.test_client()
        userinfo = _mock_google_userinfo('persist@test.com', sub='sub-persist')
        token = {'userinfo': userinfo}

        with patch('app.auth.google.oauth') as mock_oauth:
            mock_google = MagicMock()
            mock_google.authorize_access_token.return_value = token
            mock_oauth.create_client.return_value = mock_google

            client.get('/api/auth/google/callback')

        # Multiple requests should still be authenticated
        for _ in range(3):
            resp = client.get('/api/auth/me')
            assert resp.status_code == 200
            assert resp.get_json()['email'] == 'persist@test.com'


class TestGoogleOAuthEndpointsPublic:
    """Verify Google OAuth endpoints are in the public allowlist."""

    def test_google_start_no_auth_required(self, app):
        client = app.test_client()
        resp = client.get('/api/auth/google/start')
        assert resp.status_code != 401

    def test_google_callback_no_auth_required(self, app):
        """Callback should not return 401 even without session."""
        client = app.test_client()
        with patch('app.auth.google.oauth') as mock_oauth:
            mock_google = MagicMock()
            mock_google.authorize_access_token.side_effect = Exception('no state')
            mock_oauth.create_client.return_value = mock_google

            resp = client.get('/api/auth/google/callback')
            # Should be 302 redirect, NOT 401
            assert resp.status_code != 401
