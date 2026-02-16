"""
Settings Routes - Get and update user settings.
"""

from flask import Blueprint, jsonify, request
from app.models import Settings
from app.storage_paths import get_download_dir

bp = Blueprint('settings', __name__)


@bp.route('/settings', methods=['GET'])
def get_settings():
    """Get current settings."""
    settings = Settings.get_all()
    settings['download_dir'] = str(get_download_dir())
    return jsonify(settings)


@bp.route('/settings', methods=['POST'])
def update_settings():
    """Update settings."""
    data = request.get_json(silent=True) or {}

    settings_data = {}
    if 'default_format' in data:
        settings_data['default_format'] = data.get('default_format', 'm4a')
    if 'default_quality' in data:
        settings_data['default_quality'] = data.get('default_quality', '320')
    if 'check_duplicates' in data:
        settings_data['check_duplicates'] = str(data.get('check_duplicates', True)).lower()
    if 'skip_duplicates' in data:
        settings_data['skip_duplicates'] = str(data.get('skip_duplicates', True)).lower()
    if 'download_dir' in data:
        settings_data['download_dir'] = str(data.get('download_dir', '') or '').strip()

    updated = Settings.update_all(settings_data) if settings_data else Settings.get_all()
    updated['download_dir'] = str(get_download_dir())
    return jsonify(updated)
