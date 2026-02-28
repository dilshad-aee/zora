"""
Routes package for Zora.
Registers all Flask blueprints.
"""

from .api import bp as api_bp
from .download import bp as download_bp
from .history import bp as history_bp
from .playlists import bp as playlists_bp
from .queue import bp as queue_bp
from .search import bp as search_bp
from .settings import bp as settings_bp
from .stream import bp as stream_bp
from .spotify_import import bp as spotify_import_bp

__all__ = [
    'api_bp', 'download_bp', 'history_bp', 'playlists_bp',
    'queue_bp', 'search_bp', 'settings_bp', 'stream_bp',
    'spotify_import_bp',
]
