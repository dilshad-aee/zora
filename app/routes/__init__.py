"""
Routes package for YT Music Downloader.
Registers all Flask blueprints.
"""

from .api import bp as api_bp
from .queue import bp as queue_bp
from .history import bp as history_bp
from .playlists import bp as playlists_bp
from .settings import bp as settings_bp

__all__ = ['api_bp', 'queue_bp', 'history_bp', 'playlists_bp', 'settings_bp']
