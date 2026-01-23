"""
Flask Web Application for YouTube Music Downloader.

Features:
- YouTube Search
- Download Queue
- Settings Management
- Duplicate Detection
- Persistent History
- Audio Player
"""

import os
import re
import json
import uuid
import subprocess
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory

import yt_dlp

from app import YTMusicDownloader
from app.exceptions import (
    DownloadError,
    PlaylistError,
    FFmpegError,
    NetworkError,
    InvalidURLError
)
from app.utils import is_valid_url, is_playlist, format_duration, sanitize_filename


app = Flask(__name__)
app.secret_key = os.urandom(24)

# ==================== Paths ====================
BASE_DIR = os.path.dirname(__file__)
DOWNLOAD_DIR = os.path.join(BASE_DIR, 'downloads')
HISTORY_FILE = os.path.join(BASE_DIR, 'history.json')
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')

# ==================== State ====================
downloads = {}  # Active downloads
download_queue = []  # Pending downloads
queue_lock = threading.Lock()
queue_processing = False

# ==================== Settings ====================
DEFAULT_SETTINGS = {
    'default_format': 'm4a',
    'default_quality': '320',
    'output_dir': './downloads',
    'check_duplicates': True,
    'theme': 'dark'
}

def load_settings():
    """Load settings from JSON file."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                # Merge with defaults
                return {**DEFAULT_SETTINGS, **settings}
        except:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Save settings to JSON file."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

# ==================== History ====================
def load_history():
    """Load download history from JSON file."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(history):
    """Save download history to JSON file."""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

def add_to_history(item):
    """Add item to persistent history."""
    history = load_history()
    history.insert(0, {
        'id': item.get('id'),
        'title': item.get('title'),
        'thumbnail': item.get('thumbnail'),
        'filename': item.get('filename'),
        'format': item.get('format'),
        'quality': item.get('quality'),
        'duration': item.get('duration'),
        'file_size': item.get('file_size'),
        'output_dir': item.get('output_dir'),
        'completed_at': item.get('completed_at'),
        'uploader': item.get('uploader'),
        'video_id': item.get('video_id'),
    })
    history = history[:100]  # Keep last 100
    save_history(history)

# ==================== Duplicate Detection ====================
def check_duplicate(title, audio_format):
    """Check if file already exists in downloads folder."""
    if not title:
        return False, None
    
    filename = sanitize_filename(title) + '.' + audio_format.lower()
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    
    if os.path.exists(filepath):
        return True, filename
    
    # Also check history by title
    history = load_history()
    for item in history:
        if item.get('title', '').lower() == title.lower():
            return True, item.get('filename')
    
    return False, None

# ==================== Routes ====================
@app.route('/')
def index():
    """Render main page."""
    return render_template('index.html')


@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    """Get or update settings."""
    if request.method == 'GET':
        settings = load_settings()
        settings['download_dir'] = os.path.abspath(DOWNLOAD_DIR)
        settings['history_count'] = len(load_history())
        settings['queue_count'] = len(download_queue)
        return jsonify(settings)
    else:
        data = request.get_json()
        settings = load_settings()
        
        # Update allowed fields
        if 'default_format' in data:
            settings['default_format'] = data['default_format']
        if 'default_quality' in data:
            settings['default_quality'] = data['default_quality']
        if 'check_duplicates' in data:
            settings['check_duplicates'] = data['check_duplicates']
        if 'theme' in data:
            settings['theme'] = data['theme']
        
        if save_settings(settings):
            return jsonify({'success': True, 'settings': settings})
        else:
            return jsonify({'error': 'Failed to save settings'}), 500


@app.route('/api/search', methods=['POST'])
def search_youtube():
    """Search YouTube for videos."""
    data = request.get_json()
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'Search query is required'}), 400
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch10',  # Get 10 results
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch10:{query}", download=False)
            
            if not results or 'entries' not in results:
                return jsonify({'results': []})
            
            formatted_results = []
            for entry in results['entries']:
                if entry:
                    formatted_results.append({
                        'id': entry.get('id'),
                        'title': entry.get('title'),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                        'thumbnail': entry.get('thumbnail') or f"https://i.ytimg.com/vi/{entry.get('id')}/mqdefault.jpg",
                        'duration': entry.get('duration'),
                        'duration_str': format_duration(entry.get('duration', 0)),
                        'uploader': entry.get('uploader') or entry.get('channel'),
                        'view_count': entry.get('view_count', 0),
                    })
            
            return jsonify({'results': formatted_results})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/check-duplicate', methods=['POST'])
def check_duplicate_route():
    """Check if a song is already downloaded."""
    data = request.get_json()
    title = data.get('title', '')
    audio_format = data.get('format', 'm4a')
    
    is_duplicate, existing_file = check_duplicate(title, audio_format)
    
    return jsonify({
        'is_duplicate': is_duplicate,
        'existing_file': existing_file
    })


@app.route('/api/info', methods=['POST'])
def get_info():
    """Get video/playlist info without downloading."""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    if not is_valid_url(url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    try:
        downloader = YTMusicDownloader(output_dir=DOWNLOAD_DIR, quiet=True)
        info = downloader.get_info(url)
        
        settings = load_settings()
        audio_format = settings.get('default_format', 'm4a')
        
        # Check for duplicate
        is_dup, existing = check_duplicate(info.get('title'), audio_format)
        
        result = {
            'title': info.get('title', 'Unknown'),
            'thumbnail': info.get('thumbnail'),
            'duration': info.get('duration'),
            'duration_str': format_duration(info.get('duration', 0)),
            'uploader': info.get('uploader') or info.get('artist', 'Unknown'),
            'is_playlist': 'entries' in info,
            'view_count': info.get('view_count', 0),
            'upload_date': info.get('upload_date', ''),
            'video_id': info.get('id'),
            'is_duplicate': is_dup and settings.get('check_duplicates', True),
            'existing_file': existing,
        }
        
        if 'entries' in info:
            entries = info.get('entries', [])
            result['track_count'] = len(entries)
            result['tracks'] = [
                {'title': e.get('title', 'Unknown'), 'duration': format_duration(e.get('duration', 0))}
                for e in entries[:10] if e
            ]
        
        return jsonify(result)
        
    except InvalidURLError:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== Queue System ====================
@app.route('/api/queue/add', methods=['POST'])
def add_to_queue():
    """Add item to download queue."""
    data = request.get_json()
    url = data.get('url', '').strip()
    title = data.get('title', 'Unknown')
    thumbnail = data.get('thumbnail', '')
    audio_format = data.get('format', load_settings().get('default_format', 'm4a'))
    quality = data.get('quality', '320')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    queue_item = {
        'id': str(uuid.uuid4())[:8],
        'url': url,
        'title': title,
        'thumbnail': thumbnail,
        'format': audio_format.upper(),
        'quality': quality + 'kbps',
        'status': 'queued',
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    with queue_lock:
        download_queue.append(queue_item)
    
    # Start queue processing if not already running
    start_queue_processing()
    
    return jsonify({'success': True, 'queue_item': queue_item, 'position': len(download_queue)})


@app.route('/api/queue')
def get_queue():
    """Get current download queue."""
    return jsonify({
        'queue': download_queue,
        'active': [d for d in downloads.values() if d.get('status') in ['pending', 'downloading', 'processing']],
        'total': len(download_queue)
    })


@app.route('/api/queue/clear', methods=['POST'])
def clear_queue():
    """Clear the download queue."""
    with queue_lock:
        download_queue.clear()
    return jsonify({'success': True})


@app.route('/api/queue/remove/<item_id>', methods=['POST'])
def remove_from_queue(item_id):
    """Remove item from queue."""
    with queue_lock:
        for i, item in enumerate(download_queue):
            if item['id'] == item_id:
                download_queue.pop(i)
                return jsonify({'success': True})
    return jsonify({'error': 'Item not found'}), 404


def start_queue_processing():
    """Start processing the queue in background."""
    global queue_processing
    if not queue_processing:
        queue_processing = True
        thread = threading.Thread(target=process_queue, daemon=True)
        thread.start()


def process_queue():
    """Process download queue sequentially."""
    global queue_processing
    
    while True:
        with queue_lock:
            if not download_queue:
                queue_processing = False
                return
            
            # Get next item
            queue_item = download_queue[0]
        
        # Process this item
        queue_item['status'] = 'downloading'
        
        try:
            settings = load_settings()
            job_id = queue_item['id']
            
            # Create download entry
            downloads[job_id] = {
                'id': job_id,
                'url': queue_item['url'],
                'status': 'downloading',
                'progress': 0,
                'title': queue_item['title'],
                'thumbnail': queue_item['thumbnail'],
                'format': queue_item['format'],
                'quality': queue_item['quality'],
                'output_dir': os.path.abspath(DOWNLOAD_DIR),
            }
            
            # Download
            downloader = YTMusicDownloader(
                output_dir=DOWNLOAD_DIR,
                audio_format=queue_item['format'].lower(),
                quality=queue_item['quality'].replace('kbps', ''),
                quiet=True
            )
            
            result = downloader.download(queue_item['url'])
            
            if result.get('success'):
                downloads[job_id]['status'] = 'completed'
                downloads[job_id]['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                add_to_history(downloads[job_id])
            else:
                downloads[job_id]['status'] = 'error'
                downloads[job_id]['error'] = result.get('error', 'Unknown error')
                
        except Exception as e:
            if job_id in downloads:
                downloads[job_id]['status'] = 'error'
                downloads[job_id]['error'] = str(e)
        
        # Remove from queue
        with queue_lock:
            if download_queue and download_queue[0]['id'] == queue_item['id']:
                download_queue.pop(0)


# ==================== Download ====================
@app.route('/api/download', methods=['POST'])
def start_download():
    """Start a new download."""
    data = request.get_json()
    url = data.get('url', '').strip()
    audio_format = data.get('format', 'm4a')
    quality = data.get('quality', '320')
    force = data.get('force', False)  # Force download even if duplicate
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    if not is_valid_url(url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    # Check duplicate if not forced
    settings = load_settings()
    if settings.get('check_duplicates', True) and not force:
        try:
            downloader = YTMusicDownloader(output_dir=DOWNLOAD_DIR, quiet=True)
            info = downloader.get_info(url)
            is_dup, existing = check_duplicate(info.get('title'), audio_format)
            if is_dup:
                return jsonify({
                    'is_duplicate': True,
                    'title': info.get('title'),
                    'existing_file': existing,
                    'message': 'This song already exists. Use force=true to download anyway.'
                }), 409
        except:
            pass
    
    job_id = str(uuid.uuid4())[:8]
    downloads[job_id] = {
        'id': job_id,
        'url': url,
        'status': 'pending',
        'progress': 0,
        'title': 'Fetching info...',
        'error': None,
        'is_playlist': is_playlist(url),
        'format': audio_format.upper(),
        'quality': quality + 'kbps',
        'output_dir': os.path.abspath(DOWNLOAD_DIR),
        'started_at': None,
        'completed_at': None,
    }
    
    thread = threading.Thread(
        target=background_download,
        args=(job_id, url, audio_format, quality),
        daemon=True
    )
    thread.start()
    
    return jsonify({'job_id': job_id})


def background_download(job_id: str, url: str, audio_format: str, quality: str):
    """Background download task."""
    downloads[job_id]['started_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def on_progress(info):
        downloads[job_id]['status'] = 'downloading'
        downloads[job_id]['progress'] = info.get('percent', 0)
        downloads[job_id]['speed'] = info.get('speed', 0)
        downloads[job_id]['eta'] = info.get('eta', 0)
        downloads[job_id]['total_bytes'] = info.get('total_bytes', 0)
    
    def on_complete(info):
        downloads[job_id]['status'] = 'processing'
        downloads[job_id]['progress'] = 100
        downloads[job_id]['filename'] = os.path.basename(info.get('filename', ''))
    
    try:
        downloader = YTMusicDownloader(
            output_dir=DOWNLOAD_DIR,
            audio_format=audio_format,
            quality=quality,
            on_progress=on_progress,
            on_complete=on_complete,
            quiet=True
        )
        
        info = downloader.get_info(url)
        downloads[job_id]['title'] = info.get('title', 'Unknown')
        downloads[job_id]['thumbnail'] = info.get('thumbnail')
        downloads[job_id]['duration'] = info.get('duration', 0)
        downloads[job_id]['uploader'] = info.get('uploader') or info.get('artist', 'Unknown')
        downloads[job_id]['video_id'] = info.get('id')
        
        result = downloader.download(url)
        
        if result.get('success'):
            downloads[job_id]['status'] = 'completed'
            downloads[job_id]['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if result.get('type') == 'single':
                expected_file = os.path.join(DOWNLOAD_DIR, f"{info.get('title', 'unknown')}.{audio_format}")
                if os.path.exists(expected_file):
                    downloads[job_id]['file_size'] = os.path.getsize(expected_file)
                    downloads[job_id]['filename'] = os.path.basename(expected_file)
            
            add_to_history(downloads[job_id])
        else:
            downloads[job_id]['status'] = 'error'
            downloads[job_id]['error'] = result.get('error', 'Unknown error')
            
    except (DownloadError, PlaylistError, NetworkError, FFmpegError, InvalidURLError) as e:
        downloads[job_id]['status'] = 'error'
        downloads[job_id]['error'] = str(e)
    except Exception as e:
        downloads[job_id]['status'] = 'error'
        downloads[job_id]['error'] = f'Unexpected error: {e}'


@app.route('/api/status/<job_id>')
def get_status(job_id: str):
    """Get download status."""
    if job_id not in downloads:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(downloads[job_id])


@app.route('/api/downloads')
def list_downloads():
    """List all active download jobs."""
    return jsonify(list(downloads.values()))


@app.route('/api/history')
def get_history():
    """Get persistent download history."""
    return jsonify(load_history())


@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    """Clear download history."""
    save_history([])
    return jsonify({'success': True})


@app.route('/api/files')
def list_files():
    """List all downloaded files."""
    files = []
    if os.path.exists(DOWNLOAD_DIR):
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(filepath):
                ext = os.path.splitext(filename)[1].lower()
                if ext in ['.m4a', '.mp3', '.opus', '.flac', '.wav', '.ogg', '.aac']:
                    files.append({
                        'filename': filename,
                        'size': os.path.getsize(filepath),
                        'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M'),
                    })
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify(files)


@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    """Open downloads folder in system file manager."""
    try:
        folder_path = os.path.abspath(DOWNLOAD_DIR)
        os.makedirs(folder_path, exist_ok=True)
        
        if os.name == 'nt':
            os.startfile(folder_path)
        elif os.uname().sysname == 'Darwin':
            subprocess.run(['open', folder_path])
        else:
            subprocess.run(['xdg-open', folder_path])
        
        return jsonify({'success': True, 'path': folder_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/downloads/<filename>')
def serve_download(filename):
    """Serve downloaded files for download."""
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


@app.route('/play/<filename>')
def play_audio(filename):
    """Stream audio file for playback."""
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    ext = os.path.splitext(filename)[1].lower()
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
    
    return send_from_directory(DOWNLOAD_DIR, filename, mimetype=mime_type)


if __name__ == '__main__':
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print("\n🎵 YouTube Music Downloader")
    print("=" * 40)
    print("Open http://localhost:5000 in your browser")
    print(f"Downloads folder: {os.path.abspath(DOWNLOAD_DIR)}")
    print("=" * 40 + "\n")
    app.run(debug=True, port=5000)
