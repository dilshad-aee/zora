"""
Feed Routes — Personalized feed with song sets.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

bp = Blueprint('feed', __name__)


@bp.route('/feed', methods=['GET'])
@login_required
def get_feed():
    """Get personalized feed with song sets."""
    from app.services.recommendation import recommendation_engine
    max_sets = request.args.get('max_sets', 6, type=int)
    set_size = request.args.get('set_size', 12, type=int)
    sets = recommendation_engine.generate_feed(current_user.id, max_sets=max_sets, set_size=set_size)
    return jsonify({'sets': sets})
