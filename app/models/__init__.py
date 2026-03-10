"""
Models package for YT Music Downloader.
"""

from .database import db, init_db
from .download import Download
from .playlist import Playlist, PlaylistSong
from .playlist_category import PlaylistCategory
from .playlist_like import PlaylistLike
from .settings import Settings
from .user import User
from .audit_log import AuditLog, log_action
from .password_reset import PasswordResetToken
from .user_preference import UserPreference
from .spotify_import import SpotifyImportJob, SpotifyImportTrack
from .song_like import SongLike
from .play_event import PlayEvent
from .user_taste import UserTaste

__all__ = [
    'db', 'init_db', 'Download', 'Playlist', 'PlaylistSong',
    'PlaylistCategory', 'PlaylistLike', 'Settings', 'User',
    'AuditLog', 'log_action', 'PasswordResetToken', 'UserPreference',
    'SpotifyImportJob', 'SpotifyImportTrack',
    'SongLike', 'PlayEvent', 'UserTaste',
]
