"""
Stream Routes - Audio playback, thumbnails, and file downloads.
"""

import os
import re

from flask import Blueprint, jsonify, send_from_directory
from flask_login import login_required

from app.auth.decorators import admin_required
from app.storage_paths import get_download_dir, get_thumbnails_dir
from app.download_preferences import (
    get_default_download_preferences,
    get_preferred_audio_exts,
)

bp = Blueprint('stream', __name__)

BROWSER_SAFE_AUDIO_EXTS = {'.m4a', '.mp3', '.aac', '.ogg', '.wav'}


def _audio_ext_rank(ext: str, preferred_exts=None) -> int:
    """Return deterministic extension preference rank (lower is better)."""
    order = preferred_exts or get_preferred_audio_exts()
    normalized = str(ext or '').lower()
    try:
        return order.index(normalized)
    except ValueError:
        return len(order)


def _resolve_playable_filename(requested_filename: str):
    """
    Resolve a filename to an existing playable audio file.

    Supports fallback when DB has stale names like `.webm` while disk has `.m4a`.
    """
    safe_name = os.path.basename(requested_filename or '')
    if not safe_name:
        return None
    download_dir = get_download_dir()
    preferred_exts = get_preferred_audio_exts()

    requested_path = download_dir / safe_name
    if (
        requested_path.exists()
        and requested_path.is_file()
        and requested_path.suffix.lower() in preferred_exts
    ):
        return requested_path.name

    # 1) Same stem, different extension
    stem = requested_path.stem
    for ext in preferred_exts:
        candidate = download_dir / f"{stem}{ext}"
        if candidate.exists() and candidate.is_file():
            return candidate.name

    # 2) Match by YouTube ID in filename: "... [VIDEO_ID].ext"
    match = re.search(r'\[([A-Za-z0-9_-]{11})\]', stem)
    if match:
        video_id = match.group(1)
        candidates = [
            p for p in download_dir.glob(f"* [{video_id}].*")
            if p.is_file()
        ]
        if candidates:
            candidates.sort(key=lambda p: _audio_ext_rank(p.suffix, preferred_exts))
            return candidates[0].name

    return None


def _convert_audio_to_m4a(filename: str):
    """Convert an audio file variant to .m4a for broad browser playback support."""
    path = get_download_dir() / filename
    if not path.exists() or not path.is_file():
        return filename

    if path.suffix.lower() == '.m4a':
        return filename

    target = path.with_suffix('.m4a')
    if target.exists() and target.is_file():
        return target.name

    import shutil
    import subprocess

    if not shutil.which('ffmpeg'):
        return filename

    _, default_quality = get_default_download_preferences()
    target_bitrate = f'{default_quality}k'

    cmd = [
        'ffmpeg',
        '-y',
        '-i',
        str(path),
        '-vn',
        '-c:a',
        'aac',
        '-b:a', target_bitrate,
        str(target),
    ]
    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    if target.exists() and target.stat().st_size > 0:
        return target.name

    return filename


def _ensure_browser_compatible_audio(filename: str):
    """
    Ensure returned file is broadly browser-compatible.

    Converts non-browser-safe variants to `.m4a` on demand when possible.
    """
    path = get_download_dir() / filename
    if not path.exists() or not path.is_file():
        return filename

    ext = path.suffix.lower()
    if ext in BROWSER_SAFE_AUDIO_EXTS:
        return filename

    return _convert_audio_to_m4a(filename)


@bp.route('/downloads/<filename>')
@admin_required
def serve_download(filename):
    """Serve downloaded files for download."""
    return send_from_directory(str(get_download_dir()), filename, as_attachment=True)


@bp.route('/api/thumbnails/<filename>')
@login_required
def serve_thumbnail(filename):
    """Serve downloaded thumbnails."""
    return send_from_directory(str(get_thumbnails_dir()), filename)


@bp.route('/play/<filename>')
@login_required
def play_audio(filename):
    """Stream audio file for playback."""
    resolved_filename = _resolve_playable_filename(filename)
    if not resolved_filename:
        return jsonify({'error': 'File not found'}), 404

    resolved_filename = _ensure_browser_compatible_audio(resolved_filename)

    download_dir = get_download_dir()
    filepath = download_dir / resolved_filename
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404

    ext = filepath.suffix.lower()
    mime_types = {
        '.m4a': 'audio/mp4',
        '.mp3': 'audio/mpeg',
        '.opus': 'audio/ogg',
        '.flac': 'audio/flac',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.aac': 'audio/aac',
        '.webm': 'audio/webm',
        '.mka': 'audio/x-matroska',
    }
    mime_type = mime_types.get(ext, 'audio/mpeg')

    return send_from_directory(str(download_dir), resolved_filename, mimetype=mime_type)
