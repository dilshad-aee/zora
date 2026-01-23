"""
Settings Routes - Get and update user settings.
"""

from flask import Blueprint, jsonify, request
from app.models import Settings
from config import config

bp = Blueprint('settings', __name__)


@bp.route('/settings', methods=['GET'])
def get_settings():
    """Get current settings."""
    settings = Settings.get_all()
    settings['download_dir'] = str(config.DOWNLOAD_DIR)
    return jsonify(settings)


@bp.route('/settings', methods=['POST'])
def update_settings():
    """Update settings."""
    data = request.get_json()
    
    settings_data = {
        'default_format': data.get('default_format', 'm4a'),
        'default_quality': data.get('default_quality', '320'),
        'check_duplicates': str(data.get('check_duplicates', True)).lower(),
    }
    
    updated = Settings.update_all(settings_data)
    return jsonify(updated)
