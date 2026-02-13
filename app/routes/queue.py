"""
Queue Routes - Add, list, remove, clear queue items.
"""

from flask import Blueprint, jsonify, request
from app.services.queue_service import queue_service
from app.models import Download

bp = Blueprint('queue', __name__)


@bp.route('/add', methods=['POST'])
def add_to_queue():
    """Add item to download queue."""
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
    title = data.get('title', 'Unknown')
    thumbnail = data.get('thumbnail', '')
    audio_format = data.get('format', 'm4a')
    quality = data.get('quality', '320')
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
def get_queue():
    """Get queue status."""
    return jsonify(queue_service.get_all())


@bp.route('/remove/<item_id>', methods=['POST'])
def remove_from_queue(item_id: str):
    """Remove item from queue."""
    if queue_service.remove(item_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Item not found'}), 404


@bp.route('/clear', methods=['POST'])
def clear_queue():
    """Clear entire queue."""
    queue_service.clear()
    return jsonify({'success': True})
