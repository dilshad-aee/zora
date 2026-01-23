"""
Main API Routes - Home, Info, Download, Search.
"""

import os
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
        
        # Check for duplicates
        from app.models import Download
        is_duplicate, existing_file = Download.check_duplicate(
            info.get('title', ''), 
            info.get('id')
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
        # If info fetch fails, we can still try in background, or fail early
        # For now, fail early as invalid URL/Network error
        return jsonify({'error': str(e)}), 400

    # Check for duplicates (unless force=True)
    if not force:
        from app.models import Download
        is_duplicate, existing_file = Download.check_duplicate(
            info.get('title', ''),
            info.get('id')
        )
        if is_duplicate:
            return jsonify({
                'is_duplicate': True,
                'title': info.get('title'),
                'existing_file': existing_file,
                'error': 'File already exists'
            }), 409
    
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
    from app.models import Download, db
    
    queue_service.update_download(job_id, 
        started_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )
    
    def on_progress(info):
        print(f"[JOB:{job_id}] Progress: {info.get('percent', 0)}% - {info.get('filename')}", flush=True)
        queue_service.update_download(job_id,
            status='downloading',
            progress=info.get('percent', 0),
            speed=info.get('speed', 0),
            eta=info.get('eta', 0),
            total_bytes=info.get('total_bytes', 0),
            filename=os.path.basename(info.get('filename', ''))
        )
    
    def on_complete(info):
        print(f"[JOB:{job_id}] Complete: {info.get('filename')}", flush=True)
        queue_service.update_download(job_id,
            status='processing',
            progress=100,
            filename=os.path.basename(info.get('filename', ''))
        )
    
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
            queue_service.update_download(job_id,
                status='completed',
                completed_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            # Helper to save single track
            def save_track(track_info):
                try:
                    # Check existing
                    existing_id = track_info.get('id') or track_info.get('video_id')
                    if existing_id:
                        if Download.query.filter_by(video_id=existing_id).first():
                            return
                    
                    Download.add(
                        video_id=existing_id,
                        title=track_info.get('title', 'Unknown'),
                        artist=track_info.get('artist') or track_info.get('uploader', 'Unknown'),
                        filename=os.path.basename(track_info.get('filename', '')),
                        format=audio_format.upper(),
                        quality=f'{quality}kbps',
                        thumbnail=track_info.get('thumbnail', ''),
                        duration=track_info.get('duration', 0),
                        file_size=os.path.getsize(track_info.get('filename')) if track_info.get('filename') and os.path.exists(track_info.get('filename')) else 0
                    )
                except Exception as db_err:
                    print(f"DB Error saving track {track_info.get('title')}: {db_err}")

            # Need app context for DB operations
            from app import create_app
            app = create_app()
            with app.app_context():
                if result.get('type') == 'playlist':
                    print(f"[JOB:{job_id}] Saving playlist items to DB...", flush=True)
                    # For playlists, we need to try and match downloaded items to files
                    # The downloader result 'items' contains minimal info. 
                    # But on_complete was called for each.
                    # Ideally we should use the result['items'] combined with file existence
                    pass # TODO: Implement better playlist metadata saving if needed
                    
                else:
                    # Single file
                    expected_file = result.get('filename') or os.path.join(
                        str(config.DOWNLOAD_DIR),
                        f"{info.get('title', 'unknown')}.{audio_format}"
                    )
                    
                    # If file exists, update file size
                    if os.path.exists(expected_file):
                        info['filename'] = expected_file
                        info['file_size'] = os.path.getsize(expected_file)
                        queue_service.update_download(job_id,
                            file_size=info['file_size'],
                            filename=os.path.basename(expected_file)
                        )
                        save_track(info)
                    
        else:
            print(f"[JOB:{job_id}] Download process reported failure: {result.get('error')}", flush=True)
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


@bp.route('/downloads/<filename>')
def serve_download(filename):
    """Serve downloaded files for download."""
    return send_from_directory(str(config.DOWNLOAD_DIR), filename, as_attachment=True)


@bp.route('/play/<filename>')
def play_audio(filename):
    """Stream audio file for playback."""
    filepath = config.DOWNLOAD_DIR / filename
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
    }
    mime_type = mime_types.get(ext, 'audio/mpeg')
    
    return send_from_directory(str(config.DOWNLOAD_DIR), filename, mimetype=mime_type)


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
    
    # Create unique session ID
    session_id = str(uuid.uuid4())[:8]
    
    # Initialize session
    playlist_download_service.create_session(session_id, selected_songs)
    
    # Start background download
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
    from app.services.playlist_download_service import playlist_download_service
    from app.downloader import YTMusicDownloader
    from app.models import Download, db
    
    session = playlist_download_service.get_session(session_id)
    if not session:
        return
    
    print(f"[PLAYLIST:{session_id}] Starting download of {session['total']} songs", flush=True)
    
    for idx, song in enumerate(session['songs']):
        print(f"[PLAYLIST:{session_id}] Processing song {idx + 1}/{session['total']}: {song['title']}", flush=True)
        
        # Update to downloading
        playlist_download_service.update_song_status(
            session_id, song['id'], 'downloading', progress=0
        )
        
        try:
            # Create downloader with progress callback
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
            
            # Download this song
            result = downloader.download_single(song['url'])
            
            if result.get('success'):
                # Mark as completed
                playlist_download_service.update_song_status(
                    session_id, song['id'], 'completed', progress=100
                )
                playlist_download_service.increment_completed(session_id)
                
                # Save to database
                Download.add(
                    video_id=result.get('id'),
                    title=result.get('title'),
                    artist=result.get('uploader'),
                    filename=result.get('filename'),
                    thumbnail=result.get('thumbnail'),
                    duration=result.get('duration', 0),
                    file_size=result.get('filesize', 0)
                )
                
                print(f"[PLAYLIST:{session_id}] ✓ Completed: {song['title']}", flush=True)
            else:
                # Mark as failed
                error_msg = result.get('error', 'Unknown error')
                playlist_download_service.update_song_status(
                    session_id, song['id'], 'failed', error=error_msg
                )
                playlist_download_service.increment_failed(session_id)
                print(f"[PLAYLIST:{session_id}] ✗ Failed: {song['title']} - {error_msg}", flush=True)
                
        except Exception as e:
            # Mark as failed
            error_msg = str(e)
            playlist_download_service.update_song_status(
                session_id, song['id'], 'failed', error=error_msg
            )
            playlist_download_service.increment_failed(session_id)
            print(f"[PLAYLIST:{session_id}] ✗ Exception: {song['title']} - {error_msg}", flush=True)
    
    final_session = playlist_download_service.get_session(session_id)
    print(f"[PLAYLIST:{session_id}] Completed! {final_session['completed']}/{final_session['total']} successful", flush=True)
