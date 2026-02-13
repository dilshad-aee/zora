"""
Main API Routes - Home, Info, Download, Search.
"""

import os
import re
import threading
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template, send_from_directory

from config import config
from app.utils import is_valid_url, is_playlist, format_duration
from app.services.youtube import YouTubeService
from app.services.queue_service import queue_service

bp = Blueprint('api', __name__)


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


@bp.route('/api/open-folder', methods=['POST'])
def open_folder():
    """Open downloads folder in system file manager."""
    import subprocess
    
    try:
        folder_path = str(config.DOWNLOAD_DIR)
        config.ensure_dirs()
        
        if os.name == 'nt':
            os.startfile(folder_path)
        elif os.uname().sysname == 'Darwin':
            subprocess.run(['open', folder_path])
        else:
            subprocess.run(['xdg-open', folder_path])
        
        return jsonify({'success': True, 'path': folder_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/playlist-download/start', methods=['POST'])
def start_playlist_download():
    """Start playlist download with session tracking."""
    import uuid
    from app.services.playlist_download_service import playlist_download_service
    
    data = request.get_json()
    selected_songs = data.get('songs', [])
    
    if not selected_songs:
        return jsonify({'error': 'No songs provided'}), 400
    
    session_id = str(uuid.uuid4())[:8]
    playlist_download_service.create_session(session_id, selected_songs)
    
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
    from app.models import Download
    
    session = playlist_download_service.get_session(session_id)
    if not session:
        return
    
    print(f"[PLAYLIST:{session_id}] Starting download of {session['total']} songs", flush=True)
    
    app = create_app()

    for idx, song in enumerate(session['songs']):
        print(f"[PLAYLIST:{session_id}] Processing song {idx + 1}/{session['total']}: {song['title']}", flush=True)

        with app.app_context():
            is_duplicate, _ = Download.check_duplicate(
                title=song.get('title', ''),
                video_id=song.get('id'),
                artist=song.get('uploader'),
                duration=song.get('duration'),
            )
        if is_duplicate:
            playlist_download_service.update_song_status(
                session_id,
                song['id'],
                'completed',
                progress=100,
            )
            playlist_download_service.increment_completed(session_id)
            continue

        playlist_download_service.update_song_status(
            session_id, song['id'], 'downloading', progress=0
        )
        
        try:
            def progress_callback(data):
                if data.get('status') == 'downloading':
                    playlist_download_service.update_song_status(
                        session_id,
                        song['id'],
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
                    session_id, song['id'], 'completed', progress=100
                )
                playlist_download_service.increment_completed(session_id)
                
                # Get thumbnail with fallback
                thumbnail = song.get('thumbnail') or result.get('thumbnail')
                if not thumbnail and song.get('id'):
                    thumbnail = f"https://i.ytimg.com/vi/{song['id']}/mqdefault.jpg"
                
                # Save to database with app context
                with app.app_context():
                    is_duplicate, _ = Download.check_duplicate(
                        title=result.get('title') or song.get('title'),
                        video_id=song.get('id') or result.get('id'),
                        artist=result.get('uploader') or song.get('uploader'),
                        duration=result.get('duration') or song.get('duration', 0),
                    )
                    if not is_duplicate:
                        Download.add(
                            video_id=song.get('id') or result.get('id'),
                            title=result.get('title') or song.get('title'),
                            artist=result.get('uploader') or song.get('uploader', 'Unknown'),
                            filename=os.path.basename(result.get('filename', '')),
                            thumbnail=thumbnail or '',
                            duration=result.get('duration') or song.get('duration', 0),
                            file_size=result.get('filesize', 0)
                        )
                
                print(f"[PLAYLIST:{session_id}] ✓ Completed: {song['title']}", flush=True)
            else:
                error_msg = result.get('error', 'Unknown error')
                playlist_download_service.update_song_status(
                    session_id, song['id'], 'failed', error=error_msg
                )
                playlist_download_service.increment_failed(session_id)
                print(f"[PLAYLIST:{session_id}] ✗ Failed: {song['title']} - {error_msg}", flush=True)
                
        except Exception as e:
            error_msg = str(e)
            playlist_download_service.update_song_status(
                session_id, song['id'], 'failed', error=error_msg
            )
            playlist_download_service.increment_failed(session_id)
            print(f"[PLAYLIST:{session_id}] ✗ Exception: {song['title']} - {error_msg}", flush=True)
    
    final_session = playlist_download_service.get_session(session_id)
    print(f"[PLAYLIST:{session_id}] Completed! {final_session['completed']}/{final_session['total']} successful", flush=True)
