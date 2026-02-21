"""
Google OAuth 2.0 routes for Zora.

Implements Authorization Code flow via Authlib.
Env vars required: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
"""

import os
from datetime import datetime

from authlib.integrations.flask_client import OAuth
from flask import Blueprint, redirect, url_for, session, jsonify
from flask_login import login_user

from app.models import db, User

bp = Blueprint('google_auth', __name__)

oauth = OAuth()

GOOGLE_CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'


def init_google_oauth(app):
    """Register the Google OAuth client with the Flask app."""
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

    if not client_id or not client_secret:
        app.logger.info('Google OAuth not configured (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing)')
        return False

    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=GOOGLE_CONF_URL,
        client_kwargs={'scope': 'openid email profile'},
    )
    return True


@bp.route('/api/auth/google/start')
def google_start():
    """Redirect user to Google consent screen."""
    google = oauth.create_client('google')
    if google is None:
        return jsonify({'error': 'Google OAuth is not configured'}), 503

    base_url = os.getenv('ZORA_BASE_URL', '').rstrip('/')
    if base_url:
        redirect_uri = f"{base_url}/api/auth/google/callback"
    else:
        redirect_uri = url_for('google_auth.google_callback', _external=True)
    return google.authorize_redirect(redirect_uri, nonce=os.urandom(16).hex())


@bp.route('/api/auth/google/callback')
def google_callback():
    """Handle the OAuth callback from Google."""
    google = oauth.create_client('google')
    if google is None:
        return redirect('/?error=google_not_configured')

    try:
        token = google.authorize_access_token()
    except Exception:
        return redirect('/?error=google_auth_failed')

    userinfo = token.get('userinfo')
    if not userinfo:
        try:
            userinfo = google.userinfo()
        except Exception:
            return redirect('/?error=google_userinfo_failed')

    email = (userinfo.get('email') or '').strip().lower()
    if not email:
        return redirect('/?error=google_no_email')

    if not userinfo.get('email_verified', False):
        return redirect('/?error=google_email_not_verified')

    google_sub = userinfo.get('sub', '')
    name = userinfo.get('name') or email.split('@')[0]
    avatar_url = userinfo.get('picture', '')

    # Account linking policy (spec §3.3)
    user = User.query.filter_by(email=email).first()

    if user:
        # Existing account — check if active
        if not user.is_active:
            return redirect('/?error=account_disabled')

        # Link Google to existing local account
        if not user.google_sub:
            user.google_sub = google_sub
        if user.auth_provider == 'local':
            user.auth_provider = 'hybrid'
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        user.email_verified = True
    else:
        # No existing account — create new user
        user = User(
            name=name,
            email=email,
            role='user',
            auth_provider='google',
            google_sub=google_sub,
            avatar_url=avatar_url,
            email_verified=True,
            is_active=True,
        )
        db.session.add(user)

    user.last_login_at = datetime.utcnow()
    db.session.commit()

    login_user(user)
    return redirect('/')
