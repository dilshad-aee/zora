"""
Admin Routes - User management and audit log viewing.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.auth.decorators import admin_required
from app.limiter import limiter
from app.models import db, User, AuditLog
from app.models.audit_log import log_action

bp = Blueprint('admin', __name__)


@bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """List all users with pagination and search."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(per_page, 100)
    search = request.args.get('search', '').strip()

    query = User.query

    if search:
        pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                User.name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )

    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'users': [u.to_dict() for u in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })


@bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    """Get single user detail."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user.to_dict())


@bp.route('/users/<int:user_id>', methods=['PATCH'])
@admin_required
@limiter.limit("10 per minute")
def update_user(user_id):
    """Update user role or active status."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'role' in data:
        new_role = data['role']
        if new_role not in ('admin', 'user'):
            return jsonify({'error': 'Role must be admin or user'}), 400

        if user.role == 'admin' and new_role == 'user':
            admin_count = User.query.filter_by(role='admin', is_active=True).count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot demote the last admin'}), 409

        old_role = user.role
        user.role = new_role
        log_action('USER_ROLE_CHANGE', target_type='user', target_id=user_id,
                   metadata={'old_role': old_role, 'new_role': new_role})

    if 'is_active' in data:
        new_status = bool(data['is_active'])

        if not new_status and user.role == 'admin':
            admin_count = User.query.filter_by(role='admin', is_active=True).count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot deactivate the last admin'}), 409

        if user.id == current_user.id and not new_status:
            return jsonify({'error': 'Cannot deactivate yourself'}), 409

        old_status = user.is_active
        user.is_active = new_status
        action = 'USER_DEACTIVATE' if not new_status else 'USER_ACTIVATE'
        log_action(action, target_type='user', target_id=user_id,
                   metadata={'old_status': old_status, 'new_status': new_status})

    db.session.commit()
    return jsonify(user.to_dict())


@bp.route('/audit-logs', methods=['GET'])
@admin_required
def list_audit_logs():
    """List audit logs with pagination and filtering."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 30, type=int)
    per_page = min(per_page, 100)
    action_filter = request.args.get('action', '').strip()
    user_filter = request.args.get('user_id', type=int)

    query = AuditLog.query

    if action_filter:
        query = query.filter(AuditLog.action == action_filter)

    if user_filter:
        query = query.filter(AuditLog.actor_user_id == user_filter)

    query = query.order_by(AuditLog.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'logs': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })
