"""
Queue Routes - Add, list, remove, clear queue items.
"""

from flask import Blueprint, jsonify, request

from app.auth.decorators import admin_required
from app.services.queue_service import queue_service
from app.models import Download
from app.download_preferences import get_default_download_preferences

bp = Blueprint('queue', __name__)


@bp.route('/add', methods=['POST'])
@admin_required
def add_to_queue():
    """Add item to download queue."""
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
    title = data.get('title', 'Unknown')
    thumbnail = data.get('thumbnail', '')
    default_format, default_quality = get_default_download_preferences()
    audio_format = str(data.get('format') or default_format).lower().lstrip('.')
    quality = str(data.get('quality') or default_quality).strip()
    video_id = data.get('video_id', '')
    artist = data.get('artist', '')
    try:
        duration = int(data.get('duration', 0) or 0)
    except (TypeError, ValueError):
        duration = 0
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    is_duplicate, existing_file = Download.check_duplicate(
        title=title,
        video_id=video_id,
        artist=artist,
        duration=duration,
    )
    if is_duplicate:
        return jsonify({
            'skipped_duplicate': True,
            'title': title,
            'existing_file': existing_file,
        })
    
    result = queue_service.add(
        url=url,
        title=title,
        thumbnail=thumbnail,
        audio_format=audio_format,
        quality=quality,
        video_id=video_id,
        artist=artist,
        duration=duration,
    )
    return jsonify(result)


@bp.route('', methods=['GET'])
@bp.route('/', methods=['GET'])
@admin_required
def get_queue():
    """Get queue status."""
    return jsonify(queue_service.get_all())


@bp.route('/remove/<item_id>', methods=['POST'])
@admin_required
def remove_from_queue(item_id: str):
    """Remove item from queue."""
    if queue_service.remove(item_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Item not found'}), 404


@bp.route('/clear', methods=['POST'])
@admin_required
def clear_queue():
    """Clear entire queue."""
    queue_service.clear()
    return jsonify({'success': True})
