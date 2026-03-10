"""
Play Event model - records song play sessions for recommendation scoring.
"""

from datetime import datetime

from .database import db


class PlayEvent(db.Model):
    """Records a song play session for recommendation scoring."""

    __tablename__ = 'play_events'
    __table_args__ = (
        db.Index('idx_play_event_user_time', 'user_id', 'started_at'),
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
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    duration_sec = db.Column(db.Integer, default=0)  # how long user actually listened
    song_duration_sec = db.Column(db.Integer, default=0)  # total song duration
    completed = db.Column(db.Boolean, default=False)  # True if listened >= 80% of song
