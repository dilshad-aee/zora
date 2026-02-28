"""
Spotify Import models — persistent job + track state for playlist imports.
"""

import uuid
from datetime import datetime, timezone
from .database import db


class SpotifyImportJob(db.Model):
    """A Spotify playlist import job."""

    __tablename__ = 'spotify_import_jobs'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    playlist_url = db.Column(db.String(500), nullable=False)
    playlist_name = db.Column(db.String(500), default='')
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    total_tracks = db.Column(db.Integer, default=0)
    downloaded = db.Column(db.Integer, default=0)
    skipped = db.Column(db.Integer, default=0)
    failed = db.Column(db.Integer, default=0)
    current_track = db.Column(db.String(500), default='')
    error_message = db.Column(db.String(1000))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime)

    tracks = db.relationship(
        'SpotifyImportTrack', backref='job', lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def to_dict(self, include_tracks=False):
        data = {
            'id': self.id,
            'playlist_url': self.playlist_url,
            'playlist_name': self.playlist_name,
            'status': self.status,
            'total_tracks': self.total_tracks,
            'downloaded': self.downloaded,
            'skipped': self.skipped,
            'failed': self.failed,
            'current_track': self.current_track,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'progress_percent': round(
                ((self.downloaded + self.skipped + self.failed) / self.total_tracks * 100)
                if self.total_tracks > 0 else 0, 1
            ),
            'match_rate': round(
                (self.downloaded / (self.downloaded + self.skipped + self.failed) * 100)
                if (self.downloaded + self.skipped + self.failed) > 0 else 0, 1
            ),
        }
        if include_tracks:
            data['tracks'] = [t.to_dict() for t in self.tracks.order_by(SpotifyImportTrack.id)]
        return data


class SpotifyImportTrack(db.Model):
    """A single track within a Spotify import job."""

    __tablename__ = 'spotify_import_tracks'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), db.ForeignKey('spotify_import_jobs.id'), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    artist = db.Column(db.String(500), default='')
    album = db.Column(db.String(500), default='')
    isrc = db.Column(db.String(20))
    duration_ms = db.Column(db.Integer, default=0)
    explicit = db.Column(db.Boolean)
    status = db.Column(db.String(20), default='pending')  # pending, matching, downloading, downloaded, skipped, failed
    video_id = db.Column(db.String(20))
    score = db.Column(db.Float)
    reason = db.Column(db.String(500))

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'artist': self.artist,
            'album': self.album,
            'isrc': self.isrc,
            'duration_ms': self.duration_ms,
            'status': self.status,
            'video_id': self.video_id,
            'score': self.score,
            'reason': self.reason,
        }
