"""
Auth decorators for role-based access control.
"""

from functools import wraps

from flask import jsonify
from flask_login import current_user, login_required


def admin_required(f):
    """Decorator that requires the user to be an authenticated admin."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def owns_playlist(param_name='playlist_id'):
    """
    Decorator that checks the current user owns the playlist.
    Ownership is strictly enforced — admin role does NOT bypass this.
    Admins manage system-level resources (categories, users) but cannot
    modify playlists they do not own.
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            from app.models import Playlist

            pid = kwargs.get(param_name)
            playlist = Playlist.query.get(pid)
            if not playlist:
                return jsonify({'error': 'Playlist not found'}), 404

            if playlist.owner_user_id != current_user.id:
                return jsonify({'error': 'Access denied — you do not own this playlist'}), 403

            return f(*args, **kwargs)
        return decorated
    return decorator

