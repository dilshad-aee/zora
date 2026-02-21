"""
Authentication package for Zora.
Flask-Login setup, user loader, and Google OAuth init.
"""

from flask_login import LoginManager

login_manager = LoginManager()


def init_auth(app):
    """Initialize authentication with Flask app."""
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import jsonify
        return jsonify({'error': 'Authentication required'}), 401

    # Initialize Google OAuth (no-op if env vars not set)
    from app.auth.google import init_google_oauth
    init_google_oauth(app)
