"""
Auth Routes - Signup, login, logout, profile.
"""

import os
import re
from datetime import datetime

from flask import Blueprint, jsonify, request, make_response
from flask_login import current_user, login_required, login_user, logout_user

from app.limiter import limiter
from app.models import db, User

bp = Blueprint('auth', __name__)


def _is_valid_email(email):
    """Basic email format validation."""
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))


@bp.route('/api/auth/signup', methods=['POST'])
@limiter.limit("3 per minute")
def signup():
    """Create a new user account."""
    data = request.get_json(silent=True) or {}

    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if not email or not _is_valid_email(email):
        return jsonify({'error': 'Valid email is required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    if password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    user = User(
        name=name,
        email=email,
        role='user',
        auth_provider='local',
        email_verified=False,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    # Sync preferences into session and cookie
    from app.routes.preferences import load_prefs_into_session, _set_prefs_cookie
    prefs = load_prefs_into_session(user.id)
    response = make_response(jsonify(user.to_dict()), 201)
    _set_prefs_cookie(response, prefs)
    return response


@bp.route('/api/auth/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    """Login with email and password."""
    data = request.get_json(silent=True) or {}

    email = str(data.get('email', '')).strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid email or password'}), 401

    if not user.is_active:
        return jsonify({'error': 'Account is disabled'}), 403

    login_user(user)
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    # Sync preferences into session and cookie
    from app.routes.preferences import load_prefs_into_session, _set_prefs_cookie
    prefs = load_prefs_into_session(user.id)
    response = make_response(jsonify(user.to_dict()))
    _set_prefs_cookie(response, prefs)
    return response


@bp.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    """Logout current user."""
    logout_user()
    return jsonify({'success': True})


@bp.route('/api/auth/me', methods=['GET'])
@login_required
def me():
    """Get current user profile."""
    return jsonify(current_user.to_dict())


@bp.route('/api/auth/password/change', methods=['POST'])
@login_required
@limiter.limit("3 per minute")
def change_password():
    """Change current user's password."""
    data = request.get_json(silent=True) or {}

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect'}), 400

    if len(new_password) < 8:
        return jsonify({'error': 'New password must be at least 8 characters'}), 400

    current_user.set_password(new_password)
    current_user.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True})


@bp.route('/api/auth/profile', methods=['PATCH'])
@login_required
def update_profile():
    """Update current user's profile (name only)."""
    data = request.get_json(silent=True) or {}

    name = data.get('name')
    if name is not None:
        name = str(name).strip()
        if not name:
            return jsonify({'error': 'Name cannot be empty'}), 400
        if len(name) > 100:
            return jsonify({'error': 'Name is too long'}), 400
        current_user.name = name

    current_user.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(current_user.to_dict())


@bp.route('/api/auth/password/reset/request', methods=['POST'])
@limiter.limit("3 per minute")
def request_password_reset():
    """Request a password reset email."""
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    # Always return success to prevent email enumeration
    user = User.query.filter_by(email=email).first()
    if not user or not user.is_active:
        return jsonify({'success': True, 'message': 'If an account with that email exists, a reset link has been sent.'})

    # Only allow reset for users with local passwords
    if user.auth_provider == 'google':
        return jsonify({'success': True, 'message': 'If an account with that email exists, a reset link has been sent.'})

    from app.models import PasswordResetToken
    token_obj, plain_token = PasswordResetToken.create_for_user(user)

    # Build reset URL
    base_url = os.getenv('ZORA_BASE_URL', 'http://localhost:5001')
    reset_url = f"{base_url}/?reset_token={plain_token}"

    # Send email or log to console
    _send_reset_email(user, reset_url)

    return jsonify({'success': True, 'message': 'If an account with that email exists, a reset link has been sent.'})


@bp.route('/api/auth/password/reset/confirm', methods=['POST'])
@limiter.limit("10 per minute")
def confirm_password_reset():
    """Confirm password reset with token."""
    data = request.get_json(silent=True) or {}
    token_str = str(data.get('token', '')).strip()
    new_password = data.get('new_password', '')

    if not token_str:
        return jsonify({'error': 'Reset token is required'}), 400
    if len(new_password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    from app.models import PasswordResetToken
    token_obj = PasswordResetToken.validate_token(token_str)
    if not token_obj:
        return jsonify({'error': 'Invalid or expired reset token'}), 400

    user = token_obj.user
    if not user.is_active:
        return jsonify({'error': 'Account is disabled'}), 403

    user.set_password(new_password)
    user.updated_at = datetime.utcnow()
    token_obj.used = True
    db.session.commit()

    # Log the action
    from app.models import log_action
    log_action('PASSWORD_RESET', target_type='user', target_id=user.id, user=user)

    return jsonify({'success': True, 'message': 'Password has been reset. You can now log in.'})


def _send_reset_email(user, reset_url):
    """Send password reset email via SMTP, or log to console as fallback."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')

    if not smtp_host or not smtp_user or not smtp_password:
        print(f"\n{'='*60}")
        print(f"  PASSWORD RESET LINK (SMTP not configured)")
        print(f"  User: {user.email}")
        print(f"  Link: {reset_url}")
        print(f"  Expires in 1 hour")
        print(f"{'='*60}\n")
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Zora — Password Reset'
    msg['From'] = smtp_user
    msg['To'] = user.email

    text_body = f"""Hi {user.name},

You requested a password reset for your Zora account.

Click the link below to reset your password:
{reset_url}

This link expires in 1 hour. If you didn't request this, ignore this email.

— Zora"""

    html_body = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a1a2e;">Password Reset</h2>
  <p>Hi {user.name},</p>
  <p>You requested a password reset for your Zora account.</p>
  <p style="margin: 30px 0;">
    <a href="{reset_url}"
       style="background: #6c5ce7; color: #fff; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600;">
      Reset Password
    </a>
  </p>
  <p style="color: #666; font-size: 14px;">This link expires in 1 hour. If you didn't request this, ignore this email.</p>
  <p style="color: #999; font-size: 12px;">— Zora</p>
</div>"""

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, user.email, msg.as_string())
    except Exception as e:
        print(f"⚠️  Failed to send password reset email to {user.email}: {e}")
        print(f"  Reset link: {reset_url}")
