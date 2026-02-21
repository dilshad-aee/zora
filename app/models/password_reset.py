"""
Password reset token model.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from .database import db


class PasswordResetToken(db.Model):
    """Single-use password reset token."""

    __tablename__ = 'password_reset_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(255), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref='password_reset_tokens', lazy=True)

    @staticmethod
    def hash_token(token):
        """Hash a plain token for storage."""
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @classmethod
    def create_for_user(cls, user):
        """Generate a new reset token for the given user.

        Invalidates any existing unused tokens for this user.
        Returns (model_instance, plain_token).
        """
        # Invalidate existing unused tokens
        cls.query.filter_by(user_id=user.id, used=False).update({'used': True})

        plain_token = secrets.token_urlsafe(32)
        token = cls(
            user_id=user.id,
            token_hash=cls.hash_token(plain_token),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(token)
        db.session.commit()
        return token, plain_token

    @classmethod
    def validate_token(cls, plain_token):
        """Find a valid (unused, non-expired) token.

        Returns the PasswordResetToken or None.
        """
        token_hash = cls.hash_token(plain_token)
        token = cls.query.filter_by(token_hash=token_hash, used=False).first()
        if not token:
            return None
        if token.expires_at < datetime.utcnow():
            return None
        return token
