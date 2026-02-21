"""
Playlist models for grouping downloaded songs.
"""

from datetime import datetime

from .database import db


class Playlist(db.Model):
    """User-created playlist with public/private visibility."""

    __tablename__ = 'playlists'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.String(500), default='', nullable=False)
    owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    visibility = db.Column(db.String(10), nullable=False, default='private', index=True)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey('playlist_categories.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    like_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    songs = db.relationship(
        'PlaylistSong',
        back_populates='playlist',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )
    category = db.relationship('PlaylistCategory', backref='playlists')
    owner = db.relationship('User', backref='owned_playlists')

    def to_dict(self, include_liked=False, current_user_id=None):
        """Serialize playlist for API responses."""
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'owner_user_id': self.owner_user_id,
            'owner_name': self.owner.name if self.owner else 'Unknown',
            'visibility': self.visibility,
            'category_id': self.category_id,
            'category': self.category.to_dict() if self.category else None,
            'like_count': self.like_count,
            'song_count': self.songs.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_liked and current_user_id:
            from .playlist_like import PlaylistLike
            data['liked'] = PlaylistLike.query.filter_by(
                user_id=current_user_id, playlist_id=self.id
            ).first() is not None
        return data


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
