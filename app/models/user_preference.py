"""
UserPreference model — per-user key-value preference storage.

Stores functional preferences (volume, shuffle, view mode, etc.)
that sync across devices via the user's account.
"""

from datetime import datetime

from .database import db

# Allowed preference keys with their validators
PREFERENCE_KEYS = {
    'player_volume':     lambda v: 0 <= float(v) <= 1,
    'player_shuffle':    lambda v: v in ('true', 'false'),
    'player_repeat':     lambda v: v in ('off', 'all', 'one'),
    'library_view_mode': lambda v: v in ('grid', 'list'),
    'player_haptic':     lambda v: v in ('true', 'false'),
    'default_format':    lambda v: v in ('m4a', 'mp3', 'aac', 'ogg', 'opus', 'flac', 'wav', 'webm', 'mka'),
    'default_quality':   lambda v: v.isdigit() and 64 <= int(v) <= 512,
    'theme':             lambda v: v in ('dark', 'light', 'auto'),
    # Playback resume state
    'last_track_filename':  lambda v: len(v) > 0 and len(v) <= 500,
    'last_track_title':     lambda v: len(v) <= 500,
    'last_track_artist':    lambda v: len(v) <= 500,
    'last_track_thumbnail': lambda v: len(v) <= 1000,
    'last_track_position':  lambda v: float(v) >= 0,
}


def validate_preference(key, value):
    """Validate a preference key-value pair. Returns (is_valid, error_message)."""
    if key not in PREFERENCE_KEYS:
        return False, f"Unknown preference key: {key}"
    try:
        value_str = str(value).strip()
        if not PREFERENCE_KEYS[key](value_str):
            return False, f"Invalid value for {key}: {value}"
        return True, None
    except (ValueError, TypeError):
        return False, f"Invalid value for {key}: {value}"


class UserPreference(db.Model):
    """Per-user key-value preference storage."""

    __tablename__ = 'user_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    key = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(500), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False,
                           default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'key', name='uq_user_pref'),
    )

    @classmethod
    def get_all_for_user(cls, user_id):
        """Return all preferences for a user as a dict."""
        rows = cls.query.filter_by(user_id=user_id).all()
        return {row.key: row.value for row in rows}

    @classmethod
    def get_for_user(cls, user_id, key, default=None):
        """Return a single preference value, or default if not set."""
        row = cls.query.filter_by(user_id=user_id, key=key).first()
        return row.value if row else default

    @classmethod
    def set_for_user(cls, user_id, key, value):
        """Set a single preference. Creates or updates."""
        value_str = str(value).strip()
        row = cls.query.filter_by(user_id=user_id, key=key).first()
        if row:
            row.value = value_str
            row.updated_at = datetime.utcnow()
        else:
            row = cls(user_id=user_id, key=key, value=value_str)
            db.session.add(row)
        db.session.commit()
        return row

    @classmethod
    def set_bulk_for_user(cls, user_id, prefs_dict):
        """Merge-update multiple preferences at once."""
        existing = {row.key: row for row in cls.query.filter_by(user_id=user_id).all()}

        for key, value in prefs_dict.items():
            value_str = str(value).strip()
            if key in existing:
                existing[key].value = value_str
                existing[key].updated_at = datetime.utcnow()
            else:
                db.session.add(cls(user_id=user_id, key=key, value=value_str))

        db.session.commit()
