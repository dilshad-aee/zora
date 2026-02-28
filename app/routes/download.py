"""
Download Routes - Single downloads and playlist downloads.
"""

import os
import re
import threading
from datetime import datetime

from flask import Blueprint, jsonify, request, current_app
from flask_login import current_user
from sqlalchemy import func

from app.auth.decorators import admin_required
from app.utils import is_valid_url
from app.services.youtube import YouTubeService
from app.services.queue_service import queue_service
from app.storage_paths import get_download_dir
from app.download_preferences import (
    get_default_download_preferences,
    get_preferred_audio_exts,
)
from app.routes.stream import _ensure_browser_compatible_audio

bp = Blueprint('download', __name__)


def _normalize_playlist_name(name: str) -> str:
    """Normalize playlist name and enforce DB length limits."""
    cleaned = re.sub(r'\s+', ' ', str(name or '').strip())
    return cleaned[:120]


def _build_unique_playlist_name(base_name: str) -> str:
    """Generate a unique playlist name by appending numeric suffixes."""
    from app.models import Playlist

    normalized = _normalize_playlist_name(base_name)
    if not normalized:
        normalized = datetime.now().strftime('Playlist %Y-%m-%d %H:%M')

    candidate = normalized
    suffix = 2
    while Playlist.query.filter(func.lower(Playlist.name) == candidate.lower()).first():
        suffix_text = f" ({suffix})"
        trimmed = normalized[: max(1, 120 - len(suffix_text))]
        candidate = f"{trimmed}{suffix_text}"
        suffix += 1
    return candidate


def _attach_download_to_playlist(playlist_id: int, download_id: int) -> bool:
    """Add a downloaded song to playlist if not already mapped."""
    from app.models import db, PlaylistSong

    if not playlist_id or not download_id:
        return False

    existing = PlaylistSong.query.filter_by(
        playlist_id=playlist_id,
        download_id=download_id,
    ).first()
    if existing:
        return True

    db.session.add(PlaylistSong(playlist_id=playlist_id, download_id=download_id))
    db.session.commit()
    return True


def _find_library_song_for_playlist(song: dict, existing_file: str = ''):
    """
    Resolve a song payload to an existing Download row when duplicates are skipped.
    """
    from app.models import Download

    video_id = str(song.get('id') or '').strip()
    if video_id:
        existing = Download.get_by_video_id(video_id)
        if existing:
            return existing

    filename = os.path.basename(existing_file or '')
    if filename:
        existing = Download.get_by_filename(filename)
        if existing:
            return existing

    title = song.get('title', '')
    artist = song.get('uploader')
    duration = song.get('duration')
    is_duplicate, matched_file = Download.check_duplicate(
        title=title,
        video_id=video_id,
        artist=artist,
        duration=duration,
    )
    if is_duplicate and matched_file:
        return Download.get_by_filename(matched_file)
    return None


@bp.route('/api/download', methods=['POST'])
@admin_required
def start_download():
    """Start a new download."""
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
    default_format, default_quality = get_default_download_preferences()
    audio_format = str(data.get('format') or default_format).lower().lstrip('.')
    quality = str(data.get('quality') or default_quality).strip()

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    if not is_valid_url(url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    from app.models.audit_log import log_action
    log_action('DOWNLOAD_CREATE', target_type='download', metadata={'url': url, 'format': audio_format, 'quality': quality})

    # Get info first (used for duplicate check)
    try:
        info = YouTubeService.get_info(url)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    from app.models import Download
    is_duplicate, existing_file = Download.check_duplicate(
        title=info.get('title', ''),
        video_id=info.get('id'),
        artist=info.get('uploader'),
        duration=info.get('duration'),
    )
    if is_duplicate:
        return jsonify({
            'skipped_duplicate': True,
            'title': info.get('title'),
            'existing_file': existing_file,
        }), 200

    job_id = queue_service.create_download(url, audio_format, quality)

    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_background_download,
        args=(app, job_id, url, audio_format, quality, info),
        daemon=True
    )
    thread.start()

    return jsonify({'job_id': job_id})


def _background_download(app, job_id: str, url: str, audio_format: str, quality: str, info: dict = None):
    """Background download task."""
    print(f"[JOB:{job_id}] Starting background download for {url}", flush=True)

    from app.downloader import YTMusicDownloader
    from app.models import Download

    queue_service.update_download(job_id,
        started_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

    def on_progress(prog_info):
        print(f"[JOB:{job_id}] Progress: {prog_info.get('percent', 0)}% - {prog_info.get('filename')}", flush=True)
        queue_service.update_download(job_id,
            status='downloading',
            progress=prog_info.get('percent', 0),
            speed=prog_info.get('speed', 0),
            eta=prog_info.get('eta', 0),
            total_bytes=prog_info.get('total_bytes', 0),
            filename=os.path.basename(prog_info.get('filename', ''))
        )

    def on_complete(comp_info):
        print(f"[JOB:{job_id}] Complete: {comp_info.get('filename')}", flush=True)
        queue_service.update_download(job_id,
            status='processing',
            progress=100,
            filename=os.path.basename(comp_info.get('filename', ''))
        )

    def save_track(track_info):
        """Save track to database with thumbnail fallback."""
        try:
            existing_id = track_info.get('id') or track_info.get('video_id')
            is_duplicate, _ = Download.check_duplicate(
                title=track_info.get('title', ''),
                video_id=existing_id,
                artist=track_info.get('artist') or track_info.get('uploader'),
                duration=track_info.get('duration'),
            )
            if is_duplicate:
                print(f"[JOB:{job_id}] Track already exists in library, skipping DB insert", flush=True)
                return

            thumbnail = track_info.get('thumbnail')
            if not thumbnail and track_info.get('thumbnails'):
                thumbnails = track_info.get('thumbnails', [])
                if thumbnails:
                    thumbnail = thumbnails[-1].get('url')
            if not thumbnail and existing_id:
                thumbnail = f"https://i.ytimg.com/vi/{existing_id}/mqdefault.jpg"

            print(f"[JOB:{job_id}] Saving with thumbnail: {thumbnail[:60] if thumbnail else 'NONE'}...", flush=True)

            filename = track_info.get('filename', '')
            if filename:
                filename = os.path.basename(filename)

            file_size = 0
            full_path = track_info.get('filename')
            if full_path and os.path.exists(full_path):
                file_size = os.path.getsize(full_path)

            Download.add(
                video_id=existing_id,
                title=track_info.get('title', 'Unknown'),
                artist=track_info.get('artist') or track_info.get('uploader', 'Unknown'),
                filename=filename,
                format=audio_format.upper(),
                quality=f'{quality}kbps',
                thumbnail=thumbnail or '',
                duration=track_info.get('duration', 0),
                file_size=file_size
            )
            print(f"[JOB:{job_id}] ✅ Saved to DB: {track_info.get('title')}", flush=True)

        except Exception as db_err:
            print(f"[JOB:{job_id}] ❌ DB Error: {db_err}", flush=True)
            import traceback
            traceback.print_exc()

    try:
        downloader = YTMusicDownloader(
            output_dir=str(get_download_dir()),
            audio_format=audio_format,
            quality=quality,
            on_progress=on_progress,
            on_complete=on_complete,
            quiet=False
        )

        if not info:
            print(f"[JOB:{job_id}] Fetching info...", flush=True)
            info = downloader.get_info(url)
            print(f"[JOB:{job_id}] Info fetched: {info.get('title')}", flush=True)

        print(f"[JOB:{job_id}] Info thumbnail: {info.get('thumbnail', 'NONE')[:60] if info.get('thumbnail') else 'NONE'}", flush=True)

        queue_service.update_download(job_id,
            title=info.get('title', 'Unknown'),
            thumbnail=info.get('thumbnail'),
            duration=info.get('duration', 0),
            uploader=info.get('uploader') or info.get('artist', 'Unknown'),
            video_id=info.get('id')
        )

        print(f"[JOB:{job_id}] Starting download...", flush=True)
        result = downloader.download(url)
        print(f"[JOB:{job_id}] Download result success: {result.get('success')}", flush=True)

        if result.get('success'):
            # Convert to browser-compatible format if needed
            original_filename = result.get('filename', '')
            if original_filename:
                compatible_filename = _ensure_browser_compatible_audio(
                    os.path.basename(original_filename)
                )
                if compatible_filename != os.path.basename(original_filename):
                    result['filename'] = str(
                        get_download_dir() / compatible_filename
                    )

            result_filename = os.path.basename(result.get('filename', '')) if result.get('filename') else ''
            queue_service.update_download(job_id,
                status='completed',
                completed_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                filename=result_filename
            )

            track_data = {**info, **result}

            print(f"[JOB:{job_id}] Merged track_data thumbnail: {track_data.get('thumbnail', 'NONE')[:60] if track_data.get('thumbnail') else 'NONE'}", flush=True)

            with app.app_context():
                save_track(track_data)

        else:
            print(f"[JOB:{job_id}] Download failed: {result.get('error')}", flush=True)
            queue_service.update_download(job_id,
                status='error',
                error=result.get('error', 'Unknown error')
            )

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[JOB:{job_id}] Exception: {e}", flush=True)
        queue_service.update_download(job_id,
            status='error',
            error=f'Unexpected error: {str(e)}'
        )


@bp.route('/api/status/<job_id>')
@admin_required
def get_status(job_id: str):
    """Get download status."""
    download = queue_service.get_download(job_id)
    if not download:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(download)


@bp.route('/api/downloads')
@admin_required
def list_downloads():
    """List all active download jobs."""
    return jsonify(queue_service.get_all_downloads())


@bp.route('/api/playlist-download/start', methods=['POST'])
@admin_required
def start_playlist_download():
    """Start playlist download with session tracking."""
    import uuid
    from app.services.playlist_download_service import playlist_download_service

    data = request.get_json(silent=True) or {}
    selected_songs = data.get('songs', [])
    create_playlist = bool(data.get('create_playlist'))
    playlist_name = _normalize_playlist_name(data.get('playlist_name', ''))

    if not selected_songs:
        return jsonify({'error': 'No songs provided'}), 400

    session_id = str(uuid.uuid4())[:8]
    session = playlist_download_service.create_session(session_id, selected_songs)
    session['create_playlist'] = create_playlist
    session['playlist_name'] = playlist_name
    session['playlist_id'] = None
    session['owner_user_id'] = current_user.id

    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_background_playlist_download,
        args=(app, session_id),
        daemon=True
    )
    thread.start()

    return jsonify({'session_id': session_id})


@bp.route('/api/playlist-download/status/<session_id>', methods=['GET'])
@admin_required
def get_playlist_download_status(session_id):
    """Get real-time status of playlist download."""
    from app.services.playlist_download_service import playlist_download_service

    session = playlist_download_service.get_session(session_id)

    if not session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify(session)


def _background_playlist_download(app, session_id):
    """Download playlist songs sequentially with status updates."""
    from app.services.playlist_download_service import playlist_download_service
    from app.downloader import YTMusicDownloader
    from app.models import db, Download, Playlist

    session = playlist_download_service.get_session(session_id)
    if not session:
        return

    print(f"[PLAYLIST:{session_id}] Starting download of {session['total']} songs", flush=True)

    default_format, default_quality = get_default_download_preferences()
    playlist_id = None

    if session.get('create_playlist'):
        with app.app_context():
            try:
                requested_name = session.get('playlist_name', '')
                unique_name = _build_unique_playlist_name(requested_name)
                playlist = Playlist(name=unique_name, owner_user_id=session.get('owner_user_id'))
                db.session.add(playlist)
                db.session.commit()
                playlist_id = playlist.id
                session['playlist_id'] = playlist_id
                session['playlist_name'] = playlist.name
                print(
                    f"[PLAYLIST:{session_id}] Created playlist '{playlist.name}' (id={playlist_id})",
                    flush=True,
                )
            except Exception as playlist_err:
                db.session.rollback()
                session['playlist_id'] = None
                print(
                    f"[PLAYLIST:{session_id}] Failed to create playlist: {playlist_err}",
                    flush=True,
                )

    for idx, song in enumerate(session['songs']):
        print(f"[PLAYLIST:{session_id}] Processing song {idx + 1}/{session['total']}: {song['title']}", flush=True)
        session_song_id = song.get('session_song_id') or f"{song.get('id', 'song')}::{idx}"

        with app.app_context():
            is_duplicate, existing_file = Download.check_duplicate(
                title=song.get('title', ''),
                video_id=song.get('id'),
                artist=song.get('uploader'),
                duration=song.get('duration'),
            )
            if is_duplicate and playlist_id:
                existing_download = _find_library_song_for_playlist(song, existing_file)
                if existing_download:
                    try:
                        _attach_download_to_playlist(playlist_id, existing_download.id)
                    except Exception as attach_err:
                        db.session.rollback()
                        print(
                            f"[PLAYLIST:{session_id}] Failed to map duplicate song to playlist: {attach_err}",
                            flush=True,
                        )
        if is_duplicate:
            playlist_download_service.update_song_status(
                session_id,
                session_song_id,
                'completed',
                progress=100,
            )
            playlist_download_service.increment_completed(session_id)
            continue

        playlist_download_service.update_song_status(
            session_id, session_song_id, 'downloading', progress=0
        )

        try:
            def progress_callback(data, song_key=session_song_id):
                if data.get('status') == 'downloading':
                    playlist_download_service.update_song_status(
                        session_id,
                        song_key,
                        'downloading',
                        progress=int(data.get('downloaded_bytes', 0) / max(data.get('total_bytes', 1), 1) * 100),
                        speed=data.get('speed', 0),
                        eta=data.get('eta', 0)
                    )

            downloader = YTMusicDownloader(
                output_dir=str(get_download_dir()),
                audio_format=default_format,
                quality=default_quality,
                on_progress=progress_callback
            )

            result = downloader.download_single(song['url'])

            if result.get('success'):
                # Convert to browser-compatible format if needed
                original_filename = result.get('filename', '')
                if original_filename:
                    compatible_filename = _ensure_browser_compatible_audio(
                        os.path.basename(original_filename)
                    )
                    if compatible_filename != os.path.basename(original_filename):
                        result['filename'] = str(
                            get_download_dir() / compatible_filename
                        )

            if result.get('success'):
                playlist_download_service.update_song_status(
                    session_id, session_song_id, 'completed', progress=100
                )
                playlist_download_service.increment_completed(session_id)

                thumbnail = song.get('thumbnail') or result.get('thumbnail')
                if not thumbnail and song.get('id'):
                    thumbnail = f"https://i.ytimg.com/vi/{song['id']}/mqdefault.jpg"

                with app.app_context():
                    track_title = result.get('title') or song.get('title')
                    track_video_id = song.get('id') or result.get('id')
                    track_artist = result.get('uploader') or song.get('uploader')
                    track_duration = result.get('duration') or song.get('duration', 0)
                    track_filename = os.path.basename(result.get('filename', ''))

                    is_duplicate, existing_file = Download.check_duplicate(
                        title=track_title,
                        video_id=track_video_id,
                        artist=track_artist,
                        duration=track_duration,
                    )

                    download_row = None
                    if not is_duplicate:
                        download_row = Download.add(
                            video_id=track_video_id,
                            title=track_title,
                            artist=track_artist or 'Unknown',
                            filename=track_filename,
                            thumbnail=thumbnail or '',
                            duration=track_duration,
                            file_size=result.get('filesize', 0) or 0,
                        )
                    else:
                        song_lookup_payload = {
                            'id': track_video_id,
                            'title': track_title,
                            'uploader': track_artist,
                            'duration': track_duration,
                        }
                        download_row = _find_library_song_for_playlist(
                            song_lookup_payload,
                            existing_file=existing_file or track_filename,
                        )

                    if not download_row:
                        download_row = _find_library_song_for_playlist(
                            {
                                'id': track_video_id,
                                'title': track_title,
                                'uploader': track_artist,
                                'duration': track_duration,
                            },
                            existing_file=track_filename,
                        )

                    if playlist_id and download_row:
                        try:
                            _attach_download_to_playlist(playlist_id, download_row.id)
                        except Exception as attach_err:
                            db.session.rollback()
                            print(
                                f"[PLAYLIST:{session_id}] Failed to add song to playlist: {attach_err}",
                                flush=True,
                            )

                print(f"[PLAYLIST:{session_id}] ✓ Completed: {song['title']}", flush=True)
            else:
                error_msg = result.get('error', 'Unknown error')
                playlist_download_service.update_song_status(
                    session_id, session_song_id, 'failed', error=error_msg
                )
                playlist_download_service.increment_failed(session_id)
                print(f"[PLAYLIST:{session_id}] ✗ Failed: {song['title']} - {error_msg}", flush=True)

        except Exception as e:
            error_msg = str(e)
            playlist_download_service.update_song_status(
                session_id, session_song_id, 'failed', error=error_msg
            )
            playlist_download_service.increment_failed(session_id)
            print(f"[PLAYLIST:{session_id}] ✗ Exception: {song['title']} - {error_msg}", flush=True)

    final_session = playlist_download_service.get_session(session_id)
    print(f"[PLAYLIST:{session_id}] Completed! {final_session['completed']}/{final_session['total']} successful", flush=True)
