"""
History Routes - Get and clear download history.
"""

import os
import re
import shutil
import subprocess

from flask import Blueprint, jsonify
from app.models import Download, PlaylistSong, db
from config import config

bp = Blueprint('history', __name__)


def _find_existing_audio_variant(filename: str):
    """Resolve stale DB filename to an existing audio file if possible."""
    preferred_exts = ['.m4a', '.mp3', '.aac', '.ogg', '.opus', '.flac', '.wav', '.webm', '.mka']

    safe_name = os.path.basename(filename or '')
    if not safe_name:
        return None

    requested_path = config.DOWNLOAD_DIR / safe_name
    if (
        requested_path.exists()
        and requested_path.is_file()
        and requested_path.suffix.lower() in preferred_exts
    ):
        return requested_path.name

    # 1) Same stem, different extension
    stem = requested_path.stem
    for ext in preferred_exts:
        candidate = config.DOWNLOAD_DIR / f"{stem}{ext}"
        if candidate.exists() and candidate.is_file():
            return candidate.name

    # 2) Match by YouTube video id in filename
    match = re.search(r'\[([A-Za-z0-9_-]{11})\]', stem)
    if match:
        video_id = match.group(1)
        candidates = [
            p for p in config.DOWNLOAD_DIR.glob(f"* [{video_id}].*")
            if p.is_file()
        ]
        if candidates:
            def ext_rank(path):
                ext = path.suffix.lower()
                try:
                    return preferred_exts.index(ext)
                except ValueError:
                    return len(preferred_exts)

            candidates.sort(key=ext_rank)
            return candidates[0].name

    return None


def _convert_webm_to_m4a(filename: str):
    """Convert .webm audio to .m4a for better browser compatibility."""
    source_path = config.DOWNLOAD_DIR / filename
    if source_path.suffix.lower() != '.webm':
        return filename

    target_path = source_path.with_suffix('.m4a')
    if target_path.exists() and target_path.is_file():
        return target_path.name

    if not shutil.which('ffmpeg'):
        return filename

    try:
        cmd = [
            'ffmpeg',
            '-y',
            '-i',
            str(source_path),
            '-vn',
            '-c:a',
            'aac',
            '-b:a',
            '192k',
            str(target_path),
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if target_path.exists() and target_path.stat().st_size > 0:
            try:
                source_path.unlink()
            except Exception:
                pass
            return target_path.name
    except Exception:
        return filename

    return filename


@bp.route('/history', methods=['GET'])
def get_history():
    """Get download history and auto-repair stale filenames."""
    try:
        downloads = Download.query.order_by(Download.downloaded_at.desc()).all()
        changed = False

        for download in downloads:
            if not download.filename:
                continue

            fixed_name = _find_existing_audio_variant(download.filename)

            # If no actual file exists for this record, remove stale DB row.
            if not fixed_name:
                db.session.delete(download)
                changed = True
                continue

            # If a different existing variant is found (e.g. .m4a instead of stale .webm), repair it.
            if fixed_name and fixed_name.lower().endswith('.webm') and (download.format or '').lower() == 'm4a':
                fixed_name = _convert_webm_to_m4a(fixed_name)

            if fixed_name != download.filename:
                download.filename = fixed_name
                changed = True

        if changed:
            db.session.commit()
            downloads = Download.query.order_by(Download.downloaded_at.desc()).all()

        result = []
        for row in downloads:
            result.append({
                'id': row.id,
                'video_id': row.video_id,
                'title': row.title,
                'artist': row.artist,
                'filename': row.filename,
                'format': row.format,
                'quality': row.quality,
                'thumbnail': row.thumbnail,
                'duration': row.duration,
                'file_size': row.file_size,
                'downloaded_at': row.downloaded_at.isoformat() if row.downloaded_at else None
            })

        return jsonify(result)
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/history/clear', methods=['POST'])
def clear_history():
    """Clear download history."""
    Download.clear_all()
    return jsonify({'success': True})


@bp.route('/history/delete/<int:download_id>', methods=['POST'])
def delete_download(download_id):
    """Delete a download from database and filesystem."""
    download = Download.query.get(download_id)
    if not download:
        return jsonify({'error': 'Download not found'}), 404
    
    # Delete file from filesystem
    if download.filename:
        resolved_name = _find_existing_audio_variant(download.filename) or download.filename
        filepath = config.DOWNLOAD_DIR / resolved_name
        if filepath.exists():
            try:
                filepath.unlink()
            except Exception as e:
                return jsonify({'error': f'Failed to delete file: {str(e)}'}), 500
    
    # Delete from database
    PlaylistSong.query.filter_by(download_id=download.id).delete(synchronize_session=False)
    db.session.delete(download)
    db.session.commit()
    
    return jsonify({'success': True})
