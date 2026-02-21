"""
Playlist Category model - admin-defined categories for organizing playlists.
"""

from datetime import datetime

from .database import db


class PlaylistCategory(db.Model):
    """Admin-defined playlist category."""

    __tablename__ = 'playlist_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False, unique=True)
    icon = db.Column(db.String(30), nullable=False, default='fa-music')
    color = db.Column(db.String(7), nullable=False, default='#6C5CE7')
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Serialize category for API responses."""
        return {
            'id': self.id,
            'name': self.name,
            'icon': self.icon,
            'color': self.color,
            'sort_order': self.sort_order,
        }
