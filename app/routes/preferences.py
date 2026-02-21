"""
Preferences Routes — GET and PUT per-user preferences.

Functional preferences only (volume, shuffle, view mode, etc.).
No marketing or analytics cookies.
"""

import json

from flask import Blueprint, jsonify, request, session, make_response
from flask_login import current_user, login_required

from app.models.user_preference import UserPreference, validate_preference, PREFERENCE_KEYS

bp = Blueprint('preferences', __name__)

# Non-sensitive keys that go into the zora_prefs cookie for instant UI
COOKIE_PREF_KEYS = {'library_view_mode', 'theme'}


@bp.route('/preferences', methods=['GET'])
@login_required
def get_preferences():
    """Get all preferences for the current user."""
    prefs = UserPreference.get_all_for_user(current_user.id)
    return jsonify(prefs)


@bp.route('/preferences', methods=['PUT'])
@login_required
def update_preferences():
    """Bulk-update preferences for the current user.

    Accepts a JSON dict of key-value pairs.  Merges with existing
    preferences (does not delete keys that are absent from the request).
    """
    data = request.get_json(silent=True) or {}

    if not data:
        return jsonify({'error': 'No preferences provided'}), 400

    # Validate every key-value pair
    errors = []
    clean = {}
    for key, value in data.items():
        valid, err = validate_preference(key, value)
        if not valid:
            errors.append(err)
        else:
            clean[key] = str(value).strip()

    if errors:
        return jsonify({'error': 'Invalid preferences', 'details': errors}), 400

    # Persist to DB
    UserPreference.set_bulk_for_user(current_user.id, clean)

    # Update session cache
    all_prefs = UserPreference.get_all_for_user(current_user.id)
    session['prefs'] = all_prefs

    # Build response with zora_prefs cookie for non-sensitive display prefs
    response = make_response(jsonify(all_prefs))
    _set_prefs_cookie(response, all_prefs)

    return response


def _set_prefs_cookie(response, all_prefs):
    """Set the zora_prefs cookie with non-sensitive display preferences."""
    import os

    cookie_data = {k: all_prefs[k] for k in COOKIE_PREF_KEYS if k in all_prefs}

    if cookie_data:
        response.set_cookie(
            'zora_prefs',
            json.dumps(cookie_data),
            max_age=365 * 24 * 3600,   # 1 year
            httponly=False,              # Frontend reads this
            samesite='Lax',
            secure=os.getenv('FLASK_ENV') == 'production',
            path='/',
        )


def load_prefs_into_session(user_id):
    """Load preferences from DB into Flask session. Call on login/signup."""
    prefs = UserPreference.get_all_for_user(user_id)
    session['prefs'] = prefs
    return prefs
