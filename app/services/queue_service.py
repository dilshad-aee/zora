"""
Queue Service - Background download queue processing.
"""

import threading
import uuid
from datetime import datetime
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
        self.is_processing = False
    
    def add(self, url: str, title: str, thumbnail: str = '', 
            audio_format: str = 'm4a', quality: str = '320') -> dict:
        """Add item to queue."""
        item = {
            'id': str(uuid.uuid4())[:8],
            'url': url,
            'title': title,
            'thumbnail': thumbnail,
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
        return {
            'queue': self.queue.copy(),
            'active': list(self.active_downloads.values()),
            'total': len(self.queue)
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
        return self.active_downloads.get(job_id)
    
    def get_all_downloads(self) -> list:
        """Get all active downloads."""
        return list(self.active_downloads.values())
    
    def create_download(self, url: str, audio_format: str, quality: str) -> str:
        """Create a new download job."""
        from app.utils import is_playlist
        
        job_id = str(uuid.uuid4())[:8]
        
        self.active_downloads[job_id] = {
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
        }
        
        return job_id
    
    def update_download(self, job_id: str, **kwargs):
        """Update download status."""
        if job_id in self.active_downloads:
            self.active_downloads[job_id].update(kwargs)
    
    def _start_processing(self):
        """Start queue processing thread."""
        if not self.is_processing:
            self.is_processing = True
            thread = threading.Thread(target=self._process_queue, daemon=True)
            thread.start()
    
    def _process_queue(self):
        """Process queue items sequentially."""
        from app.downloader import YTMusicDownloader
        
        while True:
            with self.queue_lock:
                if not self.queue:
                    self.is_processing = False
                    return
                
                item = self.queue[0]
            
            item['status'] = 'downloading'
            job_id = item['id']
            
            try:
                self.active_downloads[job_id] = {
                    'id': job_id,
                    'url': item['url'],
                    'status': 'downloading',
                    'progress': 0,
                    'title': item['title'],
                    'thumbnail': item['thumbnail'],
                    'format': item['format'],
                    'quality': item['quality'],
                    'output_dir': str(config.DOWNLOAD_DIR),
                }
                
                downloader = YTMusicDownloader(
                    output_dir=str(config.DOWNLOAD_DIR),
                    audio_format=item['format'].lower(),
                    quality=item['quality'].replace('kbps', ''),
                    quiet=True
                )
                
                result = downloader.download(item['url'])
                
                if result.get('success'):
                    self.active_downloads[job_id]['status'] = 'completed'
                    self.active_downloads[job_id]['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                else:
                    self.active_downloads[job_id]['status'] = 'error'
                    self.active_downloads[job_id]['error'] = result.get('error', 'Unknown error')
                    
            except Exception as e:
                if job_id in self.active_downloads:
                    self.active_downloads[job_id]['status'] = 'error'
                    self.active_downloads[job_id]['error'] = str(e)
            
            # Remove from queue
            with self.queue_lock:
                if self.queue and self.queue[0]['id'] == item['id']:
                    self.queue.pop(0)


# Singleton instance
queue_service = QueueService()
