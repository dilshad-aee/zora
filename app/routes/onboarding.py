"""
Onboarding Routes — User taste onboarding preferences.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.models import db, UserTaste

bp = Blueprint('onboarding', __name__)


@bp.route('/onboarding/options', methods=['GET'])
@login_required
def get_onboarding_options():
    """Get available languages, genres, artists for onboarding selection."""
    from app.services.recommendation import RecommendationEngine
    options = RecommendationEngine.get_onboarding_options()
    return jsonify(options)


@bp.route('/onboarding/status', methods=['GET'])
@login_required
def get_onboarding_status():
    """Check if user has completed onboarding."""
    taste = UserTaste.query.filter_by(user_id=current_user.id).first()
    return jsonify({
        'completed': taste.onboarding_completed if taste else False,
        'preferences': {
            'languages': taste.get_languages() if taste else [],
            'genres': taste.get_genres() if taste else [],
            'vibes': taste.get_vibes() if taste else [],
            'artists': taste.get_artists() if taste else [],
        } if taste else None,
    })


@bp.route('/onboarding', methods=['POST'])
@login_required
def save_onboarding():
    """Save user's onboarding preferences."""
    data = request.get_json(silent=True) or {}

    languages = [str(l).strip().lower() for l in data.get('languages', []) if str(l).strip()]
    genres = [str(g).strip().lower() for g in data.get('genres', []) if str(g).strip()]
    vibes = [str(v).strip().lower() for v in data.get('vibes', []) if str(v).strip()]
    artists = [str(a).strip() for a in data.get('artists', []) if str(a).strip()]

    taste = UserTaste.query.filter_by(user_id=current_user.id).first()
    if not taste:
        taste = UserTaste(user_id=current_user.id)
        db.session.add(taste)

    taste.set_preferences(languages=languages, genres=genres, vibes=vibes, artists=artists)
    taste.onboarding_completed = True
    db.session.commit()

    return jsonify({'success': True})
