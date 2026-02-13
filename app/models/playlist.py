"""
Playlist models for grouping downloaded songs.
"""

from datetime import datetime

from .database import db


class Playlist(db.Model):
    """User-created playlist."""

    __tablename__ = 'playlists'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    songs = db.relationship(
        'PlaylistSong',
        back_populates='playlist',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )

    def to_dict(self):
        """Serialize playlist for API responses."""
        return {
            'id': self.id,
            'name': self.name,
            'song_count': self.songs.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PlaylistSong(db.Model):
    """Mapping between playlist and downloaded song."""

    __tablename__ = 'playlist_songs'
    __table_args__ = (
        db.UniqueConstraint('playlist_id', 'download_id', name='uq_playlist_song'),
    )

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(
        db.Integer,
        db.ForeignKey('playlists.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    download_id = db.Column(
        db.Integer,
        db.ForeignKey('downloads.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    added_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    playlist = db.relationship('Playlist', back_populates='songs')
    download = db.relationship('Download')

