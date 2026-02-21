"""
Playlist Like model - tracks which users liked which playlists.
"""

from datetime import datetime

from .database import db


class PlaylistLike(db.Model):
    """User's like on a playlist."""

    __tablename__ = 'playlist_likes'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'playlist_id', name='uq_playlist_like'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    playlist_id = db.Column(
        db.Integer,
        db.ForeignKey('playlists.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
