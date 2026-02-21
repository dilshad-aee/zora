"""
Settings Routes - Get and update user settings.
"""

from flask import Blueprint, jsonify, request

from app.auth.decorators import admin_required
from app.models import Settings
from app.storage_paths import get_download_dir

bp = Blueprint('settings', __name__)


@bp.route('/settings', methods=['GET'])
@admin_required
def get_settings():
    """Get current settings."""
    settings = Settings.get_all()
    settings['download_dir'] = str(get_download_dir())
    return jsonify(settings)


@bp.route('/settings', methods=['POST'])
@admin_required
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
    if 'playlist_preview_limit' in data:
        settings_data['playlist_preview_limit'] = str(
            Settings.normalize_preview_limit(data.get('playlist_preview_limit'))
        )

    updated = Settings.update_all(settings_data) if settings_data else Settings.get_all()
    updated['download_dir'] = str(get_download_dir())
    if 'playlist_preview_limit' in updated:
        updated['playlist_preview_limit'] = Settings.normalize_preview_limit(
            updated.get('playlist_preview_limit')
        )

    from app.models.audit_log import log_action
    log_action('SETTINGS_UPDATE', target_type='settings', metadata=settings_data)

    return jsonify(updated)
