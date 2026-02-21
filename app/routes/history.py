"""
History Routes - Get and clear download history.
"""

import os
import re
from datetime import datetime

from flask import Blueprint, jsonify
from flask_login import login_required

from app.auth.decorators import admin_required
from app.models import Download, PlaylistSong, db
from app.storage_paths import get_download_dir, get_thumbnails_dir
from app.download_preferences import get_preferred_audio_exts, get_default_quality_label

bp = Blueprint('history', __name__)

AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.aac', '.ogg', '.opus', '.flac', '.wav', '.webm', '.mka'}


def _audio_ext_rank(ext: str, preferred_exts=None) -> int:
    """Return deterministic extension preference rank (lower is better)."""
    order = preferred_exts or get_preferred_audio_exts()
    normalized = str(ext or '').lower()
    try:
        return order.index(normalized)
    except ValueError:
        return len(order)


def _extract_video_id_from_filename(filename: str) -> str:
    """Extract youtube id from filename pattern: title [VIDEO_ID].ext"""
    stem = os.path.splitext(os.path.basename(filename or ''))[0]
    match = re.search(r'\[([A-Za-z0-9_-]{11})\]', stem)
    return match.group(1) if match else ''


def _normalized_stem(filename: str) -> str:
    """Normalize filename stem for stable grouping."""
    stem = os.path.splitext(os.path.basename(filename or ''))[0]
    stem = re.sub(r'\s*\[[A-Za-z0-9_-]{11}\]\s*$', '', stem).strip().lower()
    stem = re.sub(r'\s+', ' ', stem)
    return stem


def _canonical_track_key(filename: str, video_id: str = '') -> str:
    """Build a stable key to group duplicate variants of the same song."""
    extracted_video_id = _extract_video_id_from_filename(filename)
    if extracted_video_id:
        return f"vid:{extracted_video_id}"

    raw_video_id = str(video_id or '').strip()
    if raw_video_id and not raw_video_id.startswith('local_'):
        return f"vid:{raw_video_id}"

    stem = _normalized_stem(filename)
    if stem:
        return f"stem:{stem}"

    return f"file:{os.path.basename(filename or '').lower()}"


def _derive_title_artist_from_filename(filename: str):
    """Best-effort title/artist extraction from filename."""
    stem = os.path.splitext(os.path.basename(filename or ''))[0]
    cleaned = re.sub(r'\s*\[[A-Za-z0-9_-]{11}\]\s*$', '', stem).strip()

    if ' - ' in cleaned:
        artist, title = cleaned.split(' - ', 1)
        return (title.strip() or cleaned, artist.strip() or 'Unknown Artist')

    return (cleaned or stem or 'Unknown', 'Unknown Artist')


def _thumbnail_for_video_id(video_id: str) -> str:
    """Resolve local thumbnail first, fallback to YouTube thumbnail URL."""
    if not video_id:
        return ''

    thumbnails_dir = get_thumbnails_dir()
    for ext in ('.webp', '.jpg', '.png', '.jpeg'):
        local_path = thumbnails_dir / f"{video_id}{ext}"
        if local_path.exists() and local_path.is_file():
            return f"/api/thumbnails/{video_id}{ext}"

    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"


def _sync_missing_download_rows(downloads: list) -> bool:
    """Ensure each audio file on disk exists in downloads table."""
    existing_filenames = {str(d.filename or '') for d in downloads}
    existing_key_rank = {}
    preferred_exts = get_preferred_audio_exts()

    for row in downloads:
        filename = str(row.filename or '')
        if not filename:
            continue
        key = _canonical_track_key(filename, getattr(row, 'video_id', ''))
        ext_rank = _audio_ext_rank(os.path.splitext(filename)[1], preferred_exts)
        current_rank = existing_key_rank.get(key)
        if current_rank is None or ext_rank < current_rank:
            existing_key_rank[key] = ext_rank

    added = False

    download_dir = get_download_dir()
    if not download_dir.exists():
        return False

    disk_audio_paths = []
    for path in download_dir.iterdir():
        if not path.is_file():
            continue
        if path.name.startswith('.'):
            continue
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        disk_audio_paths.append(path)

    # Process better-supported variants first, so .m4a/.mp3 rows win over .webm/.mka.
    disk_audio_paths.sort(key=lambda p: (_audio_ext_rank(p.suffix, preferred_exts), p.name.lower()))

    for path in disk_audio_paths:
        if path.name in existing_filenames:
            key = _canonical_track_key(path.name, _extract_video_id_from_filename(path.name))
            existing_key_rank[key] = min(
                _audio_ext_rank(path.suffix, preferred_exts),
                existing_key_rank.get(key, len(preferred_exts)),
            )
            continue

        title, artist = _derive_title_artist_from_filename(path.name)
        video_id = _extract_video_id_from_filename(path.name)
        thumbnail = _thumbnail_for_video_id(video_id)
        track_key = _canonical_track_key(path.name, video_id)
        ext_rank = _audio_ext_rank(path.suffix, preferred_exts)

        # Skip inferior variants when a better one already exists in DB.
        prior_rank = existing_key_rank.get(track_key)
        if prior_rank is not None and prior_rank <= ext_rank:
            continue

        quality_label = get_default_quality_label()

        db.session.add(Download(
            video_id=video_id or '',
            title=title,
            artist=artist,
            filename=path.name,
            format=path.suffix.lower().lstrip('.') or 'm4a',
            quality=quality_label,
            thumbnail=thumbnail,
            duration=0,
            file_size=path.stat().st_size if path.exists() else 0,
            downloaded_at=datetime.fromtimestamp(path.stat().st_mtime) if path.exists() else datetime.utcnow(),
        ))
        existing_filenames.add(path.name)
        existing_key_rank[track_key] = ext_rank
        added = True

    return added


def _find_existing_audio_variant(filename: str):
    """Resolve stale DB filename to an existing audio file if possible."""
    safe_name = os.path.basename(filename or '')
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

    # 2) Match by YouTube video id in filename
    match = re.search(r'\[([A-Za-z0-9_-]{11})\]', stem)
    if match:
        video_id = match.group(1)
        candidates = [
            p for p in download_dir.glob(f"* [{video_id}].*")
            if p.is_file()
        ]
        if candidates:
            def ext_rank(path):
                return _audio_ext_rank(path.suffix, preferred_exts)

            candidates.sort(key=ext_rank)
            return candidates[0].name

    return None


def _dedupe_library_rows(downloads: list) -> bool:
    """Keep one best DB row per canonical track and drop inferior duplicates."""
    grouped = {}
    preferred_exts = get_preferred_audio_exts()
    for row in downloads:
        filename = str(row.filename or '')
        if not filename:
            continue
        resolved_name = _find_existing_audio_variant(filename) or filename
        key = _canonical_track_key(resolved_name, row.video_id)
        grouped.setdefault(key, []).append((row, resolved_name))

    changed = False
    for items in grouped.values():
        if len(items) <= 1:
            continue

        items.sort(
            key=lambda item: (
                _audio_ext_rank(os.path.splitext(item[1])[1], preferred_exts),
                -(item[0].downloaded_at.timestamp() if item[0].downloaded_at else 0),
                item[0].id,
            )
        )

        keep_row, keep_name = items[0]
        if keep_name and keep_row.filename != keep_name:
            keep_row.filename = keep_name
            changed = True

        for duplicate_row, _ in items[1:]:
            playlist_links = PlaylistSong.query.filter_by(download_id=duplicate_row.id).all()
            for link in playlist_links:
                existing = PlaylistSong.query.filter_by(
                    playlist_id=link.playlist_id,
                    download_id=keep_row.id,
                ).first()
                if not existing:
                    db.session.add(PlaylistSong(
                        playlist_id=link.playlist_id,
                        download_id=keep_row.id,
                    ))

            PlaylistSong.query.filter_by(download_id=duplicate_row.id).delete(synchronize_session=False)
            db.session.delete(duplicate_row)
            changed = True

    return changed


@bp.route('/history', methods=['GET'])
@login_required
def get_history():
    """Get download history and auto-repair stale filenames."""
    try:
        downloads = Download.query.order_by(Download.downloaded_at.desc()).all()
        changed = False

        # Recover from accidental/empty DB state by rebuilding missing rows from audio files.
        if _sync_missing_download_rows(downloads):
            changed = True
            db.session.commit()
            Download.invalidate_duplicate_cache()
            downloads = Download.query.order_by(Download.downloaded_at.desc()).all()

        if _dedupe_library_rows(downloads):
            changed = True
            db.session.commit()
            Download.invalidate_duplicate_cache()
            downloads = Download.query.order_by(Download.downloaded_at.desc()).all()

        for download in downloads:
            if not download.filename:
                continue

            fixed_name = _find_existing_audio_variant(download.filename)

            # If no actual file exists for this record, remove stale DB row.
            if not fixed_name:
                PlaylistSong.query.filter_by(download_id=download.id).delete(synchronize_session=False)
                db.session.delete(download)
                changed = True
                continue

            if fixed_name != download.filename:
                download.filename = fixed_name
                new_ext = os.path.splitext(fixed_name)[1].lower().lstrip('.')
                if new_ext:
                    download.format = new_ext
                changed = True

            # Backfill thumbnail when missing using local file first, then YouTube fallback.
            if not str(download.thumbnail or '').strip():
                video_id = str(download.video_id or '').strip()
                if not video_id:
                    video_id = _extract_video_id_from_filename(fixed_name)
                if video_id and not video_id.startswith('local_'):
                    resolved_thumb = _thumbnail_for_video_id(video_id)
                    if resolved_thumb:
                        download.thumbnail = resolved_thumb
                        changed = True

        if changed:
            db.session.commit()
            Download.invalidate_duplicate_cache()
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
@admin_required
def clear_history():
    """Clear download history."""
    from app.models.audit_log import log_action
    log_action('HISTORY_CLEAR', target_type='history')

    Download.clear_all()
    return jsonify({'success': True})


@bp.route('/history/delete/<int:download_id>', methods=['POST'])
@admin_required
def delete_download(download_id):
    """Delete a download from database and filesystem."""
    download = Download.query.get(download_id)
    if not download:
        return jsonify({'error': 'Download not found'}), 404

    from app.models.audit_log import log_action
    log_action('SONG_DELETE', target_type='download', target_id=download_id,
               metadata={'title': download.title, 'filename': download.filename})
    
    # Delete file from filesystem
    if download.filename:
        resolved_name = _find_existing_audio_variant(download.filename) or download.filename
        filepath = get_download_dir() / resolved_name
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
