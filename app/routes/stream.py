"""
Stream Routes - Audio playback, thumbnails, and file downloads.
"""

import os
import re

from flask import Blueprint, jsonify, send_from_directory, request, Response
from flask_login import login_required
from werkzeug.http import http_date

from app.auth.decorators import admin_required
from app.storage_paths import get_download_dir, get_thumbnails_dir
from app.download_preferences import (
    get_default_download_preferences,
    get_preferred_audio_exts,
)

bp = Blueprint('stream', __name__)

BROWSER_SAFE_AUDIO_EXTS = {'.m4a', '.mp3', '.aac', '.ogg', '.wav'}

# ─── Range-request streaming (low-latency, RAM-light) ────────────────────────

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
_STREAM_CHUNK_SIZE = 64 * 1024  # 64 KiB – gentle on Termux RAM


def _iter_file_range(path, start, length):
    """Yield fixed-size chunks from *path* starting at *start* for *length* bytes."""
    with open(path, "rb") as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            data = f.read(min(_STREAM_CHUNK_SIZE, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def _parse_single_range(header, size):
    """Parse a single byte-range from a Range header. Returns (start, end) or None."""
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "" and end_s != "":
        suffix = min(int(end_s), size) if int(end_s) > 0 else 0
        if suffix <= 0:
            return None
        return (size - suffix, size - 1)
    if start_s != "":
        start = int(start_s)
        end = int(end_s) if end_s != "" else size - 1
        return (start, end) if start <= end else None
    return None


def _audio_response_with_range(path, mimetype, cache_seconds=86400):
    """Serve an audio file with HTTP Range support (206 partial / 200 full)."""
    st = os.stat(path)
    size = st.st_size
    etag = f'W/"{st.st_mtime_ns:x}-{size:x}"'
    last_modified = http_date(st.st_mtime)

    range_header = request.headers.get("Range", "")

    # 304 Not Modified (skip when Range is present)
    inm = request.headers.get("If-None-Match")
    if not range_header and inm and inm.strip() == etag:
        resp = Response(status=304)
        resp.headers["ETag"] = etag
        resp.headers["Last-Modified"] = last_modified
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["Cache-Control"] = f"private, max-age={cache_seconds}"
        return resp

    base_headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Last-Modified": last_modified,
        "Cache-Control": f"private, max-age={cache_seconds}",
    }

    byte_range = _parse_single_range(range_header, size)

    if byte_range is not None:
        start, end = byte_range
        if start >= size:
            resp = Response(status=416)
            resp.headers.update(base_headers)
            resp.headers["Content-Range"] = f"bytes */{size}"
            return resp
        end = min(end, size - 1)
        length = end - start + 1
        resp = Response(
            _iter_file_range(path, start, length) if request.method != "HEAD" else b"",
            status=206,
            mimetype=mimetype,
            direct_passthrough=True,
        )
        resp.headers.update(base_headers)
        resp.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        resp.headers["Content-Length"] = str(length)
        return resp

    # Full file (no Range header)
    resp = Response(
        _iter_file_range(path, 0, size) if request.method != "HEAD" else b"",
        status=200,
        mimetype=mimetype,
        direct_passthrough=True,
    )
    resp.headers.update(base_headers)
    resp.headers["Content-Length"] = str(size)
    return resp


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


@bp.route('/play/<filename>', methods=["GET", "HEAD"])
@login_required
def play_audio(filename):
    """Stream audio file with HTTP Range support for instant seek / low-latency start."""
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

    return _audio_response_with_range(str(filepath), mimetype=mime_type)
