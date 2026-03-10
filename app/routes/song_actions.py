"""
Song Actions Routes — Like/unlike songs and record play events.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.models import db, Download, SongLike, PlayEvent

bp = Blueprint('song_actions', __name__)


@bp.route('/songs/<int:download_id>/like', methods=['POST'])
@login_required
def like_song(download_id):
    """Like a song."""
    download = Download.query.get(download_id)
    if not download:
        return jsonify({'error': 'Song not found'}), 404

    existing = SongLike.query.filter_by(user_id=current_user.id, download_id=download_id).first()
    if existing:
        return jsonify({'liked': True})

    db.session.add(SongLike(user_id=current_user.id, download_id=download_id))
    db.session.commit()
    return jsonify({'liked': True})


@bp.route('/songs/<int:download_id>/like', methods=['DELETE'])
@login_required
def unlike_song(download_id):
    """Unlike a song."""
    existing = SongLike.query.filter_by(user_id=current_user.id, download_id=download_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
    return jsonify({'liked': False})


@bp.route('/songs/<int:download_id>/like', methods=['GET'])
@login_required
def get_like_status(download_id):
    """Get like status for a song."""
    liked = SongLike.query.filter_by(user_id=current_user.id, download_id=download_id).first() is not None
    return jsonify({'liked': liked})


@bp.route('/play-events', methods=['POST'])
@login_required
def record_play_event():
    """Record a song play event for recommendation scoring."""
    data = request.get_json(silent=True) or {}

    download_id = data.get('download_id')
    if not download_id:
        return jsonify({'error': 'download_id required'}), 400

    download = Download.query.get(download_id)
    if not download:
        return jsonify({'error': 'Song not found'}), 404

    duration_sec = max(0, int(data.get('duration_sec', 0)))
    song_duration_sec = max(0, int(data.get('song_duration_sec', download.duration or 0)))

    # Completed if listened >= 80% of song
    completed = False
    if song_duration_sec > 0 and duration_sec > 0:
        completed = (duration_sec / song_duration_sec) >= 0.8

    event = PlayEvent(
        user_id=current_user.id,
        download_id=download_id,
        duration_sec=duration_sec,
        song_duration_sec=song_duration_sec,
        completed=completed,
    )
    db.session.add(event)
    db.session.commit()

    return jsonify({'recorded': True, 'completed': completed})
