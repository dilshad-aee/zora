"""
Audit log model for tracking admin and sensitive actions.
"""

from datetime import datetime

from flask import request as flask_request
from flask_login import current_user

from .database import db


class AuditLog(db.Model):
    """Records admin and sensitive actions for audit trail."""

    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    target_type = db.Column(db.String(30), nullable=True)
    target_id = db.Column(db.String(50), nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    actor = db.relationship('User', backref='audit_logs', lazy=True)

    def to_dict(self):
        """Serialize for API responses."""
        import json
        return {
            'id': self.id,
            'actor_user_id': self.actor_user_id,
            'actor_name': self.actor.name if self.actor else None,
            'actor_email': self.actor.email if self.actor else None,
            'action': self.action,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'metadata': json.loads(self.metadata_json) if self.metadata_json else None,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


def log_action(action, target_type=None, target_id=None, metadata=None, user=None):
    """
    Record an audit log entry.

    Args:
        action: Action string (e.g. DOWNLOAD_CREATE, SETTINGS_UPDATE)
        target_type: Type of target (e.g. download, settings, user)
        target_id: ID of target entity
        metadata: Dict of extra details (stored as JSON)
        user: User performing the action (defaults to current_user)
    """
    import json

    actor = user or (current_user if current_user and current_user.is_authenticated else None)

    ip = None
    ua = None
    try:
        ip = flask_request.remote_addr
        ua = str(flask_request.user_agent)[:500] if flask_request.user_agent else None
    except RuntimeError:
        pass

    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        metadata_json=json.dumps(metadata) if metadata else None,
        ip_address=ip,
        user_agent=ua,
    )
    db.session.add(entry)
    db.session.commit()
    return entry
