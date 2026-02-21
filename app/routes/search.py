"""
Search Routes - YouTube search and video/playlist info.
"""

from flask import Blueprint, jsonify, request

from app.auth.decorators import admin_required
from app.utils import is_valid_url, is_playlist, is_unsupported_dynamic_playlist
from app.services.youtube import YouTubeService

bp = Blueprint('search', __name__)


@bp.route('/api/info', methods=['POST'])
@admin_required
def get_info():
    """Get video/playlist information."""
    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    if not is_valid_url(url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    try:
        info = YouTubeService.get_info(url)

        from app.models import Download
        is_duplicate, existing_file = Download.check_duplicate(
            title=info.get('title', ''),
            video_id=info.get('id'),
            artist=info.get('uploader'),
            duration=info.get('duration'),
        )
        info['is_duplicate'] = is_duplicate
        info['existing_file'] = existing_file

        return jsonify(info)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/search', methods=['POST'])
@admin_required
def search():
    """Search YouTube for videos."""
    data = request.get_json()
    query = data.get('query', '').strip()

    if not query:
        return jsonify({'error': 'Search query is required'}), 400

    try:
        results = YouTubeService.search(query, limit=12)
        return jsonify({'results': results})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/playlist/items', methods=['POST'])
@admin_required
def get_playlist_items():
    """Get all items from a playlist without downloading."""
    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    if not is_playlist(url):
        return jsonify({'error': 'Invalid playlist URL'}), 400

    if is_unsupported_dynamic_playlist(url):
        return jsonify({
            'error': (
                'YouTube Mix/Radio playlists (list=RD...) are not supported. '
                'Use a normal playlist URL (list=PL... or OLAK...).'
            )
        }), 400

    try:
        items = YouTubeService.get_playlist_items(url)
        return jsonify(items)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
