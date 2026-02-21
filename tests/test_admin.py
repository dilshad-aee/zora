"""
Phase 3 — Admin panel + audit log tests.

Covers:
  - Audit log model and log_action helper
  - Admin user management API (list, get, update role, activate/deactivate)
  - Audit log viewing API
  - Last-admin protection
  - Non-admin access denied
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
def user_client(app):
    """Authenticated regular-user test client."""
    client = app.test_client()
    resp = client.post('/api/auth/signup', json={
        'name': 'Regular User',
        'email': 'user@test.com',
        'password': 'userpass1',
        'confirm_password': 'userpass1',
    })
    assert resp.status_code == 201
    return client


@pytest.fixture(scope='module')
def guest(app):
    """Unauthenticated test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Audit Log Model
# ---------------------------------------------------------------------------

class TestAuditLogModel:
    def test_log_action_creates_entry(self, app, admin_client):
        with app.app_context():
            from app.models import AuditLog, db
            from app.models.audit_log import log_action

            initial_count = AuditLog.query.count()

            # Log via the admin client request context
            resp = admin_client.get('/api/admin/users')
            assert resp.status_code == 200

            # Manually log an action
            with app.test_request_context():
                from app.models import User
                admin = User.query.filter_by(email='admin@test.com').first()
                log_action('TEST_ACTION', target_type='test', target_id='1',
                           metadata={'key': 'value'}, user=admin)

            entry = AuditLog.query.filter_by(action='TEST_ACTION').first()
            assert entry is not None
            assert entry.target_type == 'test'
            assert entry.target_id == '1'
            assert entry.actor_user_id == admin.id

    def test_log_action_to_dict(self, app):
        with app.app_context():
            from app.models import AuditLog
            entry = AuditLog.query.filter_by(action='TEST_ACTION').first()
            d = entry.to_dict()
            assert d['action'] == 'TEST_ACTION'
            assert d['metadata'] == {'key': 'value'}
            assert d['actor_name'] is not None
            assert 'created_at' in d


# ---------------------------------------------------------------------------
# Admin User Management
# ---------------------------------------------------------------------------

class TestAdminUserManagement:
    def test_guest_cannot_access_admin(self, guest):
        resp = guest.get('/api/admin/users')
        assert resp.status_code == 401

    def test_user_cannot_access_admin(self, user_client):
        resp = user_client.get('/api/admin/users')
        assert resp.status_code == 403

    def test_admin_list_users(self, admin_client):
        resp = admin_client.get('/api/admin/users')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'users' in data
        assert 'total' in data
        assert data['total'] >= 2  # admin + regular user

    def test_admin_list_users_search(self, admin_client):
        resp = admin_client.get('/api/admin/users?search=Regular')
        data = resp.get_json()
        assert data['total'] == 1
        assert data['users'][0]['name'] == 'Regular User'

    def test_admin_get_user(self, app, admin_client):
        with app.app_context():
            from app.models import User
            user = User.query.filter_by(email='user@test.com').first()

        resp = admin_client.get(f'/api/admin/users/{user.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['email'] == 'user@test.com'

    def test_admin_get_nonexistent_user(self, admin_client):
        resp = admin_client.get('/api/admin/users/99999')
        assert resp.status_code == 404

    def test_admin_change_user_role(self, app, admin_client):
        with app.app_context():
            from app.models import User
            user = User.query.filter_by(email='user@test.com').first()
            user_id = user.id

        resp = admin_client.patch(f'/api/admin/users/{user_id}', json={'role': 'admin'})
        assert resp.status_code == 200
        assert resp.get_json()['role'] == 'admin'

        # Change back to user
        resp = admin_client.patch(f'/api/admin/users/{user_id}', json={'role': 'user'})
        assert resp.status_code == 200
        assert resp.get_json()['role'] == 'user'

    def test_admin_invalid_role(self, app, admin_client):
        with app.app_context():
            from app.models import User
            user = User.query.filter_by(email='user@test.com').first()

        resp = admin_client.patch(f'/api/admin/users/{user.id}', json={'role': 'superadmin'})
        assert resp.status_code == 400

    def test_cannot_demote_last_admin(self, app, admin_client):
        with app.app_context():
            from app.models import User
            admin = User.query.filter_by(email='admin@test.com').first()

        resp = admin_client.patch(f'/api/admin/users/{admin.id}', json={'role': 'user'})
        assert resp.status_code == 409
        assert 'last admin' in resp.get_json()['error'].lower()

    def test_admin_deactivate_user(self, app, admin_client):
        with app.app_context():
            from app.models import User
            user = User.query.filter_by(email='user@test.com').first()
            user_id = user.id

        resp = admin_client.patch(f'/api/admin/users/{user_id}', json={'is_active': False})
        assert resp.status_code == 200
        assert resp.get_json()['is_active'] is False

        # Reactivate
        resp = admin_client.patch(f'/api/admin/users/{user_id}', json={'is_active': True})
        assert resp.status_code == 200
        assert resp.get_json()['is_active'] is True

    def test_cannot_deactivate_last_admin(self, app, admin_client):
        with app.app_context():
            from app.models import User
            admin = User.query.filter_by(email='admin@test.com').first()

        resp = admin_client.patch(f'/api/admin/users/{admin.id}', json={'is_active': False})
        assert resp.status_code == 409

    def test_role_change_creates_audit_log(self, app, admin_client):
        with app.app_context():
            from app.models import AuditLog
            logs = AuditLog.query.filter_by(action='USER_ROLE_CHANGE').all()
            assert len(logs) >= 1


# ---------------------------------------------------------------------------
# Audit Log Viewing
# ---------------------------------------------------------------------------

class TestAuditLogViewing:
    def test_guest_cannot_view_audit_logs(self, guest):
        resp = guest.get('/api/admin/audit-logs')
        assert resp.status_code == 401

    def test_user_cannot_view_audit_logs(self, user_client):
        resp = user_client.get('/api/admin/audit-logs')
        assert resp.status_code == 403

    def test_admin_list_audit_logs(self, admin_client):
        resp = admin_client.get('/api/admin/audit-logs')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'logs' in data
        assert 'total' in data
        assert data['total'] >= 1

    def test_admin_filter_audit_logs_by_action(self, admin_client):
        resp = admin_client.get('/api/admin/audit-logs?action=USER_ROLE_CHANGE')
        data = resp.get_json()
        for log in data['logs']:
            assert log['action'] == 'USER_ROLE_CHANGE'

    def test_audit_log_has_actor_info(self, admin_client):
        resp = admin_client.get('/api/admin/audit-logs')
        data = resp.get_json()
        for log in data['logs']:
            if log['actor_user_id']:
                assert log['actor_name'] is not None
