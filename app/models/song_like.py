"""
Song Like model - tracks which users liked which songs.
"""

from datetime import datetime

from .database import db


class SongLike(db.Model):
    """User's like on a song."""

    __tablename__ = 'song_likes'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'download_id', name='uq_song_like'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    download_id = db.Column(
        db.Integer,
        db.ForeignKey('downloads.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
