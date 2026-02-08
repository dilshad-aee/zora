"""
History Routes - Get and clear download history.
"""

from flask import Blueprint, jsonify
from app.models import Download

bp = Blueprint('history', __name__)


@bp.route('/history', methods=['GET'])
def get_history():
    """Get download history using raw SQL."""
    import sqlite3
    from config import config
    
    try:
        db_path = config.BASE_DIR / 'data.db'
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, video_id, title, artist, filename, format, quality, 
                   thumbnail, duration, file_size, downloaded_at
            FROM downloads
            ORDER BY downloaded_at DESC
        """)
        
        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                'id': row['id'],
                'video_id': row['video_id'],
                'title': row['title'],
                'artist': row['artist'],
                'filename': row['filename'],
                'format': row['format'],
                'quality': row['quality'],
                'thumbnail': row['thumbnail'],
                'duration': row['duration'],
                'file_size': row['file_size'],
                'downloaded_at': row['downloaded_at']
            })
        
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/history/clear', methods=['POST'])
def clear_history():
    """Clear download history."""
    Download.clear_all()
    return jsonify({'success': True})


@bp.route('/history/delete/<int:download_id>', methods=['POST'])
def delete_download(download_id):
    """Delete a download from database and filesystem."""
    from app.models import db
    from config import config
    
    download = Download.query.get(download_id)
    if not download:
        return jsonify({'error': 'Download not found'}), 404
    
    # Delete file from filesystem
    if download.filename:
        filepath = config.DOWNLOAD_DIR / download.filename
        if filepath.exists():
            try:
                filepath.unlink()
            except Exception as e:
                return jsonify({'error': f'Failed to delete file: {str(e)}'}), 500
    
    # Delete from database
    db.session.delete(download)
    db.session.commit()
    
    return jsonify({'success': True})
