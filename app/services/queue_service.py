"""
Queue Service - Background download queue processing.
"""

import os
import threading
import uuid
from datetime import datetime, timedelta
from config import config


class QueueService:
    """Thread-safe download queue management."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        """Initialize queue state."""
        self.queue = []
        self.active_downloads = {}
        self.queue_lock = threading.Lock()
        self.active_lock = threading.Lock()
        self.is_processing = False
        self.completed_retention_seconds = 120
    
    def _now_str(self) -> str:
        """Return a consistent timestamp string."""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _parse_dt(self, value: str):
        """Parse timestamp strings used by queue records."""
        try:
            return datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')
        except Exception:
            return None

    def _set_active_download(self, job_id: str, payload: dict):
        """Create/replace active download entry with updated timestamp."""
        entry = dict(payload or {})
        entry['updated_at'] = self._now_str()
        with self.active_lock:
            self.active_downloads[job_id] = entry

    def _patch_active_download(self, job_id: str, **kwargs):
        """Update active download entry and refresh updated timestamp."""
        with self.active_lock:
            if job_id in self.active_downloads:
                self.active_downloads[job_id].update(kwargs)
                self.active_downloads[job_id]['updated_at'] = self._now_str()

    def _cleanup_finished_downloads(self):
        """Drop terminal jobs after retention to avoid unbounded growth."""
        cutoff = datetime.now() - timedelta(seconds=self.completed_retention_seconds)
        stale_ids = []

        with self.active_lock:
            for job_id, job in self.active_downloads.items():
                if job.get('status') not in {'completed', 'error', 'skipped'}:
                    continue

                stamp = self._parse_dt(job.get('updated_at') or job.get('completed_at'))
                if not stamp:
                    continue

                if stamp <= cutoff:
                    stale_ids.append(job_id)

            for job_id in stale_ids:
                self.active_downloads.pop(job_id, None)
    
    def add(
        self,
        url: str,
        title: str,
        thumbnail: str = '',
        audio_format: str = 'm4a',
        quality: str = '320',
        video_id: str = '',
        artist: str = '',
        duration: int = 0,
    ) -> dict:
        """Add item to queue."""
        item = {
            'id': str(uuid.uuid4())[:8],
            'url': url,
            'title': title,
            'thumbnail': thumbnail,
            'video_id': video_id,
            'artist': artist,
            'duration': duration,
            'format': audio_format.upper(),
            'quality': f'{quality}kbps',
            'status': 'queued',
            'added_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        with self.queue_lock:
            self.queue.append(item)
            position = len(self.queue)
        
        # Start processing if not already running
        self._start_processing()
        
        return {'queue_item': item, 'position': position}
    
    def get_all(self) -> dict:
        """Get queue status."""
        self._cleanup_finished_downloads()
        with self.queue_lock:
            queue_snapshot = self.queue.copy()
            total = len(self.queue)
        with self.active_lock:
            active_snapshot = list(self.active_downloads.values())

        return {
            'queue': queue_snapshot,
            'active': active_snapshot,
            'total': total
        }
    
    def remove(self, item_id: str) -> bool:
        """Remove item from queue."""
        with self.queue_lock:
            for i, item in enumerate(self.queue):
                if item['id'] == item_id:
                    self.queue.pop(i)
                    return True
        return False
    
    def clear(self):
        """Clear entire queue."""
        with self.queue_lock:
            self.queue.clear()
    
    def get_download(self, job_id: str) -> dict:
        """Get active download status."""
        self._cleanup_finished_downloads()
        with self.active_lock:
            return self.active_downloads.get(job_id)
    
    def get_all_downloads(self) -> list:
        """Get all active downloads."""
        self._cleanup_finished_downloads()
        with self.active_lock:
            return list(self.active_downloads.values())
    
    def create_download(self, url: str, audio_format: str, quality: str) -> str:
        """Create a new download job."""
        from app.utils import is_playlist
        
        job_id = str(uuid.uuid4())[:8]
        
        self._set_active_download(job_id, {
            'id': job_id,
            'url': url,
            'status': 'pending',
            'progress': 0,
            'title': 'Fetching info...',
            'error': None,
            'is_playlist': is_playlist(url),
            'format': audio_format.upper(),
            'quality': f'{quality}kbps',
            'output_dir': str(config.DOWNLOAD_DIR),
            'started_at': None,
            'completed_at': None,
        })
        
        return job_id
    
    def update_download(self, job_id: str, **kwargs):
        """Update download status."""
        self._patch_active_download(job_id, **kwargs)
    
    def _start_processing(self):
        """Start queue processing thread."""
        if not self.is_processing:
            self.is_processing = True
            thread = threading.Thread(target=self._process_queue, daemon=True)
            thread.start()
    
    def _process_queue(self):
        """Process queue items sequentially."""
        from app import create_app
        from app.downloader import YTMusicDownloader
        from app.models import Download

        app = create_app()
        
        while True:
            with self.queue_lock:
                if not self.queue:
                    self.is_processing = False
                    return
                
                item = self.queue[0]
            
            item['status'] = 'downloading'
            job_id = item['id']

            with app.app_context():
                is_duplicate, existing_file = Download.check_duplicate(
                    title=item.get('title', ''),
                    video_id=item.get('video_id'),
                    artist=item.get('artist'),
                    duration=item.get('duration'),
                )
                if is_duplicate:
                    self._set_active_download(job_id, {
                        'id': job_id,
                        'url': item['url'],
                        'status': 'skipped',
                        'progress': 100,
                        'title': item['title'],
                        'thumbnail': item['thumbnail'],
                        'format': item['format'],
                        'quality': item['quality'],
                        'output_dir': str(config.DOWNLOAD_DIR),
                        'existing_file': existing_file,
                        'completed_at': self._now_str(),
                    })
                    item['status'] = 'skipped'

                    with self.queue_lock:
                        if self.queue and self.queue[0]['id'] == item['id']:
                            self.queue.pop(0)
                    continue
            
            try:
                self._set_active_download(job_id, {
                    'id': job_id,
                    'url': item['url'],
                    'status': 'downloading',
                    'progress': 0,
                    'title': item['title'],
                    'thumbnail': item['thumbnail'],
                    'video_id': item.get('video_id'),
                    'artist': item.get('artist'),
                    'duration': item.get('duration'),
                    'format': item['format'],
                    'quality': item['quality'],
                    'output_dir': str(config.DOWNLOAD_DIR),
                })
                
                downloader = YTMusicDownloader(
                    output_dir=str(config.DOWNLOAD_DIR),
                    audio_format=item['format'].lower(),
                    quality=item['quality'].replace('kbps', ''),
                    quiet=True
                )
                
                result = downloader.download(item['url'])
                
                if result.get('success'):
                    result_filename = os.path.basename(result.get('filename', '') or '')

                    # Persist queue downloads to library/history DB.
                    with app.app_context():
                        track_title = result.get('title') or item.get('title') or 'Unknown'
                        track_video_id = item.get('video_id') or result.get('id') or ''
                        track_artist = (
                            result.get('artist')
                            or result.get('uploader')
                            or item.get('artist')
                            or 'Unknown'
                        )
                        track_duration = result.get('duration') or item.get('duration', 0)
                        track_thumbnail = result.get('thumbnail') or item.get('thumbnail') or ''

                        is_duplicate, _ = Download.check_duplicate(
                            title=track_title,
                            video_id=track_video_id,
                            artist=track_artist,
                            duration=track_duration,
                        )
                        if not is_duplicate:
                            file_size = 0
                            if result_filename:
                                file_path = config.DOWNLOAD_DIR / result_filename
                                if file_path.exists():
                                    file_size = file_path.stat().st_size

                            Download.add(
                                video_id=track_video_id,
                                title=track_title,
                                artist=track_artist,
                                filename=result_filename,
                                format=item['format'],
                                quality=item['quality'],
                                thumbnail=track_thumbnail,
                                duration=track_duration,
                                file_size=file_size,
                            )

                    self._patch_active_download(
                        job_id,
                        status='completed',
                        completed_at=self._now_str(),
                        filename=result_filename,
                    )
                else:
                    self._patch_active_download(
                        job_id,
                        status='error',
                        error=result.get('error', 'Unknown error'),
                    )
                    
            except Exception as e:
                self._patch_active_download(job_id, status='error', error=str(e))
            
            # Remove from queue
            with self.queue_lock:
                if self.queue and self.queue[0]['id'] == item['id']:
                    self.queue.pop(0)


# Singleton instance
queue_service = QueueService()
