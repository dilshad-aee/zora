"""
Zora - YouTube Music Downloader

Flask application factory and initialization.
"""

import os
from flask import Flask
from config import config


def create_app():
    """Create and configure the Flask application."""
    
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')
    
    # Configuration
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Ensure directories exist
    config.ensure_dirs()
    
    # Initialize database
    from app.models import init_db, migrate_from_json
    init_db(app)
    
    # Migrate from JSON if exists
    history_json = config.BASE_DIR / 'history.json'
    if history_json.exists():
        migrate_from_json(app, history_json)
    
    # Register blueprints
    from app.routes.api import bp as api_bp
    from app.routes.queue import bp as queue_bp
    from app.routes.history import bp as history_bp
    from app.routes.playlists import bp as playlists_bp
    from app.routes.settings import bp as settings_bp
    
    app.register_blueprint(api_bp)
    app.register_blueprint(queue_bp, url_prefix='/api/queue')
    app.register_blueprint(history_bp, url_prefix='/api')
    app.register_blueprint(playlists_bp, url_prefix='/api')
    app.register_blueprint(settings_bp, url_prefix='/api')
    
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
