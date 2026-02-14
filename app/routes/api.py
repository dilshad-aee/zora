"""
Main API Routes - Home, Info, Download, Search.
"""

import os
import re
import threading
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template, send_from_directory
from sqlalchemy import func

from config import config
from app.utils import is_valid_url, is_playlist, format_duration
from app.services.youtube import YouTubeService
from app.services.queue_service import queue_service

bp = Blueprint('api', __name__)


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


@bp.route('/')
def index():
    """Serve the main application page."""
    return render_template('index.html')


@bp.route('/api/info', methods=['POST'])
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

        # Always check duplicates using strong multi-parameter matching.
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
def get_playlist_items():
    """Get all items from a playlist without downloading."""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # Verify it's a playlist URL
    if not is_playlist(url):
        return jsonify({'error': 'Invalid playlist URL'}), 400
    
    try:
        items = YouTubeService.get_playlist_items(url)
        return jsonify(items)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/download', methods=['POST'])
def start_download():
    """Start a new download."""
    data = request.get_json()
    url = data.get('url', '').strip()
    audio_format = data.get('format', 'm4a')
    quality = data.get('quality', '320')
    force = data.get('force', False)
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    if not is_valid_url(url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    # Get info first (used for duplicate check and optimization)
    try:
        info = YouTubeService.get_info(url)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    # Always skip duplicates; no force override.
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
    
    # Create download job
    job_id = queue_service.create_download(url, audio_format, quality)
    
    # Start download in background
    thread = threading.Thread(
        target=_background_download,
        args=(job_id, url, audio_format, quality, info),
        daemon=True
    )
    thread.start()
    
    return jsonify({'job_id': job_id})


def _background_download(job_id: str, url: str, audio_format: str, quality: str, info: dict = None):
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
            
            # Get thumbnail with multiple fallbacks
            thumbnail = track_info.get('thumbnail')
            if not thumbnail and track_info.get('thumbnails'):
                thumbnails = track_info.get('thumbnails', [])
                if thumbnails:
                    thumbnail = thumbnails[-1].get('url')
            if not thumbnail and existing_id:
                thumbnail = f"https://i.ytimg.com/vi/{existing_id}/mqdefault.jpg"
            
            print(f"[JOB:{job_id}] Saving with thumbnail: {thumbnail[:60] if thumbnail else 'NONE'}...", flush=True)
            
            # Get filename
            filename = track_info.get('filename', '')
            if filename:
                filename = os.path.basename(filename)
            
            # Get file size
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
            output_dir=str(config.DOWNLOAD_DIR),
            audio_format=audio_format,
            quality=quality,
            on_progress=on_progress,
            on_complete=on_complete,
            quiet=False
        )
        
        # Use provided info or fetch it
        if not info:
            print(f"[JOB:{job_id}] Fetching info...", flush=True)
            info = downloader.get_info(url)
            print(f"[JOB:{job_id}] Info fetched: {info.get('title')}", flush=True)
        
        # Debug: Log thumbnail from info
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
            result_filename = os.path.basename(result.get('filename', '')) if result.get('filename') else ''
            queue_service.update_download(job_id,
                status='completed',
                completed_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                filename=result_filename
            )
            
            # Merge info (has thumbnail) with result (has filename)
            # info has: id, title, thumbnail, duration, uploader
            # result has: success, filename, title, etc.
            track_data = {**info, **result}
            
            print(f"[JOB:{job_id}] Merged track_data thumbnail: {track_data.get('thumbnail', 'NONE')[:60] if track_data.get('thumbnail') else 'NONE'}", flush=True)
            
            # Need app context for DB operations
            from app import create_app
            app = create_app()
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
def get_status(job_id: str):
    """Get download status."""
    download = queue_service.get_download(job_id)
    if not download:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(download)




@bp.route('/api/downloads')
def list_downloads():
    """List all active download jobs."""
    return jsonify(queue_service.get_all_downloads())


def _resolve_playable_filename(requested_filename: str):
    """
    Resolve a filename to an existing playable audio file.

    Supports fallback when DB has stale names like `.webm` while disk has `.m4a`.
    """
    preferred_exts = ['.m4a', '.mp3', '.aac', '.ogg', '.opus', '.flac', '.wav', '.webm', '.mka']

    safe_name = os.path.basename(requested_filename or '')
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

    # 2) Match by YouTube ID in filename: "... [VIDEO_ID].ext"
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


def _ensure_browser_compatible_audio(filename: str):
    """
    Ensure returned file is broadly browser-compatible.

    Converts lone `.webm` files to `.m4a` on demand when possible.
    """
    path = config.DOWNLOAD_DIR / filename
    if not path.exists() or path.suffix.lower() != '.webm':
        return filename

    target = path.with_suffix('.m4a')
    if target.exists() and target.is_file():
        return target.name

    import shutil
    import subprocess

    if not shutil.which('ffmpeg'):
        return filename

    cmd = [
        'ffmpeg',
        '-y',
        '-i',
        str(path),
        '-vn',
        '-c:a',
        'aac',
        '-b:a',
        '192k',
        str(target),
    ]
    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if target.exists() and target.stat().st_size > 0:
        try:
            path.unlink()
        except Exception:
            pass
        return target.name

    return filename






@bp.route('/downloads/<filename>')
def serve_download(filename):
    """Serve downloaded files for download."""
    return send_from_directory(str(config.DOWNLOAD_DIR), filename, as_attachment=True)


@bp.route('/api/thumbnails/<filename>')
def serve_thumbnail(filename):
    """Serve downloaded thumbnails."""
    return send_from_directory(str(config.THUMBNAILS_DIR), filename)


@bp.route('/play/<filename>')
def play_audio(filename):
    """Stream audio file for playback."""
    resolved_filename = _resolve_playable_filename(filename)
    if not resolved_filename:
        return jsonify({'error': 'File not found'}), 404

    resolved_filename = _ensure_browser_compatible_audio(resolved_filename)

    filepath = config.DOWNLOAD_DIR / resolved_filename
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404
    
    ext = filepath.suffix.lower()
    mime_types = {
        '.m4a': 'audio/mp4',
        '.mp3': 'audio/mpeg',
        '.opus': 'audio/opus',
        '.flac': 'audio/flac',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.aac': 'audio/aac',
        '.webm': 'audio/webm',
        '.mka': 'audio/x-matroska',
    }
    mime_type = mime_types.get(ext, 'audio/mpeg')
    
    return send_from_directory(str(config.DOWNLOAD_DIR), resolved_filename, mimetype=mime_type)


@bp.route('/api/playlist-download/start', methods=['POST'])
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
    
    thread = threading.Thread(
        target=_background_playlist_download,
        args=(session_id,),
        daemon=True
    )
    thread.start()
    
    return jsonify({'session_id': session_id})


@bp.route('/api/playlist-download/status/<session_id>', methods=['GET'])
def get_playlist_download_status(session_id):
    """Get real-time status of playlist download."""
    from app.services.playlist_download_service import playlist_download_service
    
    session = playlist_download_service.get_session(session_id)
    
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    return jsonify(session)


def _background_playlist_download(session_id):
    """Download playlist songs sequentially with status updates."""
    from app import create_app
    from app.services.playlist_download_service import playlist_download_service
    from app.downloader import YTMusicDownloader
    from app.models import db, Download, Playlist
    
    session = playlist_download_service.get_session(session_id)
    if not session:
        return
    
    print(f"[PLAYLIST:{session_id}] Starting download of {session['total']} songs", flush=True)
    
    app = create_app()
    playlist_id = None

    # Optionally auto-create a playlist that will contain all selected songs.
    if session.get('create_playlist'):
        with app.app_context():
            try:
                requested_name = session.get('playlist_name', '')
                unique_name = _build_unique_playlist_name(requested_name)
                playlist = Playlist(name=unique_name)
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
                output_dir=str(config.DOWNLOAD_DIR),
                on_progress=progress_callback
            )
            
            result = downloader.download_single(song['url'])
            
            if result.get('success'):
                playlist_download_service.update_song_status(
                    session_id, session_song_id, 'completed', progress=100
                )
                playlist_download_service.increment_completed(session_id)
                
                # Get thumbnail with fallback
                thumbnail = song.get('thumbnail') or result.get('thumbnail')
                if not thumbnail and song.get('id'):
                    thumbnail = f"https://i.ytimg.com/vi/{song['id']}/mqdefault.jpg"
                
                # Save to database with app context
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
