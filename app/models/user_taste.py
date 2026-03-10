"""
User Taste model - stores music taste preferences from onboarding.
"""

import json
from datetime import datetime

from .database import db


class UserTaste(db.Model):
    """User's music taste preferences from onboarding."""

    __tablename__ = 'user_tastes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    languages = db.Column(db.Text, default='[]')   # JSON array of preferred languages
    genres = db.Column(db.Text, default='[]')       # JSON array of preferred genres
    vibes = db.Column(db.Text, default='[]')        # JSON array of mood/vibe tags
    artists = db.Column(db.Text, default='[]')      # JSON array of favorite artists
    onboarding_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def get_languages(self):
        """Parse and return languages as a list."""
        return json.loads(self.languages or '[]')

    def get_genres(self):
        """Parse and return genres as a list."""
        return json.loads(self.genres or '[]')

    def get_vibes(self):
        """Parse and return vibes as a list."""
        return json.loads(self.vibes or '[]')

    def get_artists(self):
        """Parse and return artists as a list."""
        return json.loads(self.artists or '[]')

    def set_preferences(self, languages=None, genres=None, vibes=None, artists=None):
        """JSON encode and save preference lists."""
        if languages is not None:
            self.languages = json.dumps(languages)
        if genres is not None:
            self.genres = json.dumps(genres)
        if vibes is not None:
            self.vibes = json.dumps(vibes)
        if artists is not None:
            self.artists = json.dumps(artists)
