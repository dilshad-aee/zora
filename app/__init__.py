"""
Zora - YouTube Music Downloader

Flask application factory and initialization.
"""

import os
from datetime import timedelta
from flask import Flask, jsonify
from config import config


def _bootstrap_admin(app):
    """Create initial admin account from env vars if no users exist."""
    admin_email = os.getenv('ZORA_ADMIN_EMAIL')
    admin_password = os.getenv('ZORA_ADMIN_PASSWORD')
    admin_name = os.getenv('ZORA_ADMIN_NAME', 'Admin')
    
    with app.app_context():
        from app.models import db, User
        
        if User.query.count() > 0:
            return
        
        if not admin_email or not admin_password:
            print("⚠️  No users exist and ZORA_ADMIN_EMAIL/ZORA_ADMIN_PASSWORD not set.")
            print("   Set env vars and restart to create the admin account.")
            return
        
        admin = User(
            name=admin_name,
            email=admin_email.lower().strip(),
            role='admin',
            auth_provider='local',
            email_verified=True,
            is_active=True,
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        print(f"✅ Admin account created for {admin.email}")


def _cleanup_stuck_import_jobs(app):
    """Mark any processing/pending import jobs as failed after server restart."""
    with app.app_context():
        from app.models import db
        from app.models.spotify_import import SpotifyImportJob
        stuck = SpotifyImportJob.query.filter(
            SpotifyImportJob.status.in_(['processing', 'pending'])
        ).all()
        for job in stuck:
            job.status = 'failed'
            job.error_message = 'Server restarted during import'
            job.current_track = ''
        if stuck:
            db.session.commit()
            print(f"⚠️  Marked {len(stuck)} stuck import job(s) as failed")


def create_app(testing=False):
    """Create and configure the Flask application."""
    
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')
    
    app.config['TESTING'] = testing
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', config.SECRET_KEY)
    app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Session cookie security
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
    
    # Remember-me cookie (persists login across browser/app restarts)
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
    app.config['REMEMBER_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
    
    # Ensure directories exist
    config.ensure_dirs()
    
    # Initialize database
    from app.models import init_db
    init_db(app)
    
    # Initialize authentication
    from app.auth import init_auth
    init_auth(app)
    
    # Initialize rate limiter
    from app.limiter import limiter
    if app.config.get('TESTING'):
        app.config['RATELIMIT_ENABLED'] = False
    limiter.init_app(app)

    # Initialize CSRF protection
    # CSRF protection: SameSite=Lax cookies prevent CSRF for cross-origin
    # requests. For same-origin JSON APIs, the Content-Type check provides
    # additional protection since forms cannot send application/json.
    # Full Flask-WTF CSRFProtect is deferred to Phase 4 security hardening
    # to avoid blocking all existing POST endpoints during the transition.
    app.config['WTF_CSRF_ENABLED'] = False
    
    # Bootstrap admin on first run
    _bootstrap_admin(app)

    # Clean up stuck import jobs from previous server runs
    _cleanup_stuck_import_jobs(app)
    
    # Register blueprints
    from app.auth.routes import bp as auth_bp
    from app.auth.google import bp as google_auth_bp
    from app.routes.api import bp as api_bp
    from app.routes.download import bp as download_bp
    from app.routes.history import bp as history_bp
    from app.routes.playlists import bp as playlists_bp
    from app.routes.queue import bp as queue_bp
    from app.routes.search import bp as search_bp
    from app.routes.settings import bp as settings_bp
    from app.routes.stream import bp as stream_bp
    from app.routes.preferences import bp as preferences_bp
    from app.routes.categories import bp as categories_bp
    from app.admin.routes import bp as admin_bp
    from app.routes.spotify_import import bp as spotify_import_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(google_auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(api_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(history_bp, url_prefix='/api')
    app.register_blueprint(playlists_bp, url_prefix='/api')
    app.register_blueprint(queue_bp, url_prefix='/api/queue')
    app.register_blueprint(search_bp)
    app.register_blueprint(settings_bp, url_prefix='/api')
    app.register_blueprint(preferences_bp, url_prefix='/api')
    app.register_blueprint(categories_bp, url_prefix='/api')
    app.register_blueprint(stream_bp)
    app.register_blueprint(spotify_import_bp, url_prefix='/api/spotify-import')
    
    # Default-deny: require auth on all routes except explicit allowlist
    PUBLIC_ENDPOINTS = {
        'auth.signup',
        'auth.login',
        'google_auth.google_start',
        'google_auth.google_callback',
        'auth.request_password_reset',
        'auth.confirm_password_reset',
        'api.index',
        'static',
    }
    
    @app.before_request
    def require_auth():
        from flask import request as req
        from flask_login import current_user as cu
        
        endpoint = req.endpoint
        if endpoint is None:
            return
        if endpoint in PUBLIC_ENDPOINTS:
            return
        if cu.is_authenticated:
            return
        return jsonify({'error': 'Authentication required'}), 401
    
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
    
    # ─── PWA: serve service worker at root scope ─────────────────────────────
    @app.route('/sw.js')
    def service_worker():
        from flask import send_from_directory, make_response
        import os
        static_dir = os.path.join(app.root_path, '..', 'static')
        resp = make_response(send_from_directory(static_dir, 'sw.js'))
        resp.headers['Content-Type'] = 'application/javascript'
        resp.headers['Service-Worker-Allowed'] = '/'
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    # Also add service worker to public endpoints
    PUBLIC_ENDPOINTS.add('service_worker')

    return app


# Backwards compatibility exports
from .downloader import YTMusicDownloader
from .exceptions import (
    DownloadError,
    PlaylistError,
    NetworkError,
    FFmpegError,
    InvalidURLError
)
from .utils import (
    is_valid_url,
    is_playlist,
    sanitize_filename,
    format_duration,
    format_filesize,
    ensure_dir,
    extract_video_id
)

__all__ = [
    'create_app',
    'YTMusicDownloader',
    'DownloadError',
    'PlaylistError',
    'NetworkError',
    'FFmpegError',
    'InvalidURLError',
    'is_valid_url',
    'is_playlist',
    'sanitize_filename',
    'format_duration',
    'format_filesize',
    'ensure_dir',
    'extract_video_id',
]
