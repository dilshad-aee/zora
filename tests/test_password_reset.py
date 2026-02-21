"""
Phase 4 — Password reset + security hardening tests.

Covers:
  - Password reset token model
  - Password reset request endpoint
  - Password reset confirm endpoint
  - Security headers
  - Rate limiting presence
  - Final security checklist items
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope='module')
def app():
    """Create a fresh app with an in-memory database."""
    os.environ['ZORA_ADMIN_EMAIL'] = 'admin@test.com'
    os.environ['ZORA_ADMIN_PASSWORD'] = 'adminpass1'
    os.environ['SECRET_KEY'] = 'test-secret-key-fixed'

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
def admin_client(app):
    """Authenticated admin test client."""
    client = app.test_client()
    resp = client.post('/api/auth/login', json={
        'email': 'admin@test.com',
        'password': 'adminpass1',
    })
    assert resp.status_code == 200
    return client


@pytest.fixture(scope='module')
def test_user(app):
    """Create a regular test user for password reset tests."""
    client = app.test_client()
    resp = client.post('/api/auth/signup', json={
        'name': 'Reset User',
        'email': 'reset@test.com',
        'password': 'oldpassword123',
        'confirm_password': 'oldpassword123',
    })
    assert resp.status_code == 201
    return resp.get_json()


@pytest.fixture()
def guest(app):
    """Unauthenticated test client."""
    return app.test_client()


# ===========================================================================
# 1. Password Reset Token Model
# ===========================================================================

class TestPasswordResetTokenModel:
    """Test the PasswordResetToken model."""

    def test_create_token_for_user(self, app, test_user):
        with app.app_context():
            from app.models import User, PasswordResetToken
            user = User.query.filter_by(email='reset@test.com').first()
            assert user is not None

            token_obj, plain_token = PasswordResetToken.create_for_user(user)
            assert token_obj is not None
            assert plain_token is not None
            assert len(plain_token) > 20
            assert token_obj.user_id == user.id
            assert token_obj.used is False

    def test_validate_valid_token(self, app, test_user):
        with app.app_context():
            from app.models import User, PasswordResetToken
            user = User.query.filter_by(email='reset@test.com').first()
            _, plain_token = PasswordResetToken.create_for_user(user)

            result = PasswordResetToken.validate_token(plain_token)
            assert result is not None
            assert result.user_id == user.id

    def test_validate_invalid_token(self, app, test_user):
        with app.app_context():
            from app.models import PasswordResetToken
            result = PasswordResetToken.validate_token('bogus-token-value')
            assert result is None

    def test_token_single_use(self, app, test_user):
        with app.app_context():
            from app.models import User, PasswordResetToken, db
            user = User.query.filter_by(email='reset@test.com').first()
            token_obj, plain_token = PasswordResetToken.create_for_user(user)

            # Mark as used
            token_obj.used = True
            db.session.commit()

            result = PasswordResetToken.validate_token(plain_token)
            assert result is None

    def test_new_token_invalidates_old(self, app, test_user):
        with app.app_context():
            from app.models import User, PasswordResetToken
            user = User.query.filter_by(email='reset@test.com').first()
            _, old_token = PasswordResetToken.create_for_user(user)
            _, new_token = PasswordResetToken.create_for_user(user)

            # Old token should be invalid (marked used)
            assert PasswordResetToken.validate_token(old_token) is None
            # New token should be valid
            assert PasswordResetToken.validate_token(new_token) is not None

    def test_expired_token_rejected(self, app, test_user):
        with app.app_context():
            from datetime import datetime, timedelta
            from app.models import User, PasswordResetToken, db
            user = User.query.filter_by(email='reset@test.com').first()
            token_obj, plain_token = PasswordResetToken.create_for_user(user)

            # Force expiry
            token_obj.expires_at = datetime.utcnow() - timedelta(hours=2)
            db.session.commit()

            result = PasswordResetToken.validate_token(plain_token)
            assert result is None


# ===========================================================================
# 2. Password Reset Request Endpoint
# ===========================================================================

class TestPasswordResetRequest:
    """Test POST /api/auth/password/reset/request."""

    def test_request_reset_valid_email(self, guest, test_user):
        resp = guest.post('/api/auth/password/reset/request', json={
            'email': 'reset@test.com',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_request_reset_unknown_email(self, guest):
        """Unknown email returns success to prevent enumeration."""
        resp = guest.post('/api/auth/password/reset/request', json={
            'email': 'nonexistent@test.com',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_request_reset_no_email(self, guest):
        resp = guest.post('/api/auth/password/reset/request', json={})
        assert resp.status_code == 400

    def test_request_reset_is_public(self, guest):
        """Password reset request doesn't require authentication."""
        resp = guest.post('/api/auth/password/reset/request', json={
            'email': 'reset@test.com',
        })
        assert resp.status_code != 401


# ===========================================================================
# 3. Password Reset Confirm Endpoint
# ===========================================================================

class TestPasswordResetConfirm:
    """Test POST /api/auth/password/reset/confirm."""

    def test_confirm_reset_success(self, app, guest, test_user):
        with app.app_context():
            from app.models import User, PasswordResetToken
            user = User.query.filter_by(email='reset@test.com').first()
            _, plain_token = PasswordResetToken.create_for_user(user)

        resp = guest.post('/api/auth/password/reset/confirm', json={
            'token': plain_token,
            'new_password': 'newpassword456',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        # Verify can login with new password
        resp2 = guest.post('/api/auth/login', json={
            'email': 'reset@test.com',
            'password': 'newpassword456',
        })
        assert resp2.status_code == 200

    def test_confirm_reset_invalid_token(self, guest):
        resp = guest.post('/api/auth/password/reset/confirm', json={
            'token': 'invalid-token-value',
            'new_password': 'newpassword456',
        })
        assert resp.status_code == 400

    def test_confirm_reset_short_password(self, app, guest, test_user):
        with app.app_context():
            from app.models import User, PasswordResetToken
            user = User.query.filter_by(email='reset@test.com').first()
            _, plain_token = PasswordResetToken.create_for_user(user)

        resp = guest.post('/api/auth/password/reset/confirm', json={
            'token': plain_token,
            'new_password': 'short',
        })
        assert resp.status_code == 400

    def test_confirm_reset_used_token(self, app, guest, test_user):
        """Token cannot be reused after successful reset."""
        with app.app_context():
            from app.models import User, PasswordResetToken
            user = User.query.filter_by(email='reset@test.com').first()
            _, plain_token = PasswordResetToken.create_for_user(user)

        # First use
        resp1 = guest.post('/api/auth/password/reset/confirm', json={
            'token': plain_token,
            'new_password': 'firstreset123',
        })
        assert resp1.status_code == 200

        # Second use — should fail
        resp2 = guest.post('/api/auth/password/reset/confirm', json={
            'token': plain_token,
            'new_password': 'secondreset123',
        })
        assert resp2.status_code == 400

    def test_confirm_reset_is_public(self, guest):
        """Password reset confirm doesn't require authentication."""
        resp = guest.post('/api/auth/password/reset/confirm', json={
            'token': 'any-token',
            'new_password': 'somepassword',
        })
        assert resp.status_code != 401


# ===========================================================================
# 4. Security Headers
# ===========================================================================

class TestSecurityHeaders:
    """Every response must include security headers."""

    def test_x_content_type_options(self, guest):
        resp = guest.get('/')
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_frame_options(self, guest):
        resp = guest.get('/')
        assert resp.headers.get('X-Frame-Options') == 'DENY'

    def test_x_xss_protection(self, guest):
        resp = guest.get('/')
        assert resp.headers.get('X-XSS-Protection') == '1; mode=block'

    def test_referrer_policy(self, guest):
        resp = guest.get('/')
        assert resp.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_headers_on_api_responses(self, guest):
        resp = guest.post('/api/auth/login', json={
            'email': 'a@b.com', 'password': 'x',
        })
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
        assert resp.headers.get('X-Frame-Options') == 'DENY'


# ===========================================================================
# 5. Security Checklist Items
# ===========================================================================

class TestSecurityChecklist:
    """Verify key security properties."""

    def test_password_hash_not_in_api_response(self, guest, test_user):
        """User API responses must never expose password_hash."""
        client = guest
        resp = client.post('/api/auth/login', json={
            'email': 'reset@test.com',
            'password': 'firstreset123',
        })
        data = resp.get_json()
        assert 'password_hash' not in data

    def test_deactivated_user_locked_out(self, app, admin_client, guest):
        """Deactivated users cannot login."""
        # Create a user to deactivate
        client = app.test_client()
        resp = client.post('/api/auth/signup', json={
            'name': 'Deactivate Me',
            'email': 'deactivate@test.com',
            'password': 'testpass123',
            'confirm_password': 'testpass123',
        })
        assert resp.status_code == 201
        user_data = resp.get_json()
        user_id = user_data['id']

        # Admin deactivates the user
        resp2 = admin_client.patch(f'/api/admin/users/{user_id}', json={
            'is_active': False,
        })
        assert resp2.status_code == 200

        # Deactivated user tries to login
        resp3 = guest.post('/api/auth/login', json={
            'email': 'deactivate@test.com',
            'password': 'testpass123',
        })
        assert resp3.status_code == 403

    def test_session_cookie_config(self, app):
        """Session cookies have security attributes."""
        assert app.config['SESSION_COOKIE_HTTPONLY'] is True
        assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'

    def test_password_reset_creates_audit_log(self, app, test_user):
        """Password reset action is recorded in audit logs."""
        client = app.test_client()

        with app.app_context():
            from app.models import User, PasswordResetToken
            user = User.query.filter_by(email='reset@test.com').first()
            _, plain_token = PasswordResetToken.create_for_user(user)

        resp = client.post('/api/auth/password/reset/confirm', json={
            'token': plain_token,
            'new_password': 'auditlogtest1',
        })
        assert resp.status_code == 200

        with app.app_context():
            from app.models import AuditLog
            log = AuditLog.query.filter_by(action='PASSWORD_RESET').first()
            assert log is not None
