"""
History Routes - Get and clear download history.
"""

from flask import Blueprint, jsonify
from app.models import Download

bp = Blueprint('history', __name__)


@bp.route('/history', methods=['GET'])
def get_history():
    """Get download history."""
    downloads = Download.get_history(limit=100)
    return jsonify([d.to_dict() for d in downloads])


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
