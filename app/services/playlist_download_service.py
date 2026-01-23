"""
Playlist Download Service - Manages playlist download sessions with progress tracking.

Handles:
- Creating download sessions for playlists
- Tracking individual song status (queued, downloading, completed, failed)
- Real-time progress updates
- Session persistence during download
"""

from datetime import datetime
from typing import Dict, List, Optional


class PlaylistDownloadService:
    """Manages playlist download sessions with real-time progress tracking."""
    
    def __init__(self):
        self.active_sessions: Dict[str, dict] = {}
    
    def create_session(self, session_id: str, songs: List[dict]) -> dict:
        """
        Create a new playlist download session.
        
        Args:
            session_id: Unique session identifier
            songs: List of song dictionaries with id, title, url, etc.
            
        Returns:
            Created session dictionary
        """
        session = {
            'session_id': session_id,
            'songs': [
                {
                    'id': song['id'],
                    'title': song['title'],
                    'url': song['url'],
                    'thumbnail': song.get('thumbnail', ''),
                    'uploader': song.get('uploader', 'Unknown'),
                    'duration_str': song.get('duration_str', '0:00'),
                    'status': 'queued',  # queued, downloading, completed, failed
                    'progress': 0,
                    'speed': 0,
                    'eta': 0,
                    'error': None,
                    'job_id': None
                }
                for song in songs
            ],
            'total': len(songs),
            'completed': 0,
            'failed': 0,
            'current_index': 0,
            'started_at': datetime.now().isoformat()
        }
        
        self.active_sessions[session_id] = session
        return session
    
    def update_song_status(self, session_id: str, song_id: str, status: str, **kwargs):
        """
        Update status of a specific song in the session.
        
        Args:
            session_id: Session identifier
            song_id: Song identifier  
            status: New status (queued, downloading, completed, failed)
            **kwargs: Additional fields to update (progress, speed, eta, error)
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return
        
        for song in session['songs']:
            if song['id'] == song_id:
                song['status'] = status
                
                # Update additional fields
                if 'progress' in kwargs:
                    song['progress'] = kwargs['progress']
                if 'speed' in kwargs:
                    song['speed'] = kwargs['speed']
                if 'eta' in kwargs:
                    song['eta'] = kwargs['eta']
                if 'error' in kwargs:
                    song['error'] = kwargs['error']
                if 'job_id' in kwargs:
                    song['job_id'] = kwargs['job_id']
                
                break
    
    def increment_completed(self, session_id: str):
        """Increment completed count for session."""
        session = self.active_sessions.get(session_id)
        if session:
            session['completed'] += 1
    
    def increment_failed(self, session_id: str):
        """Increment failed count for session."""
        session = self.active_sessions.get(session_id)
        if session:
            session['failed'] += 1
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get playlist download session data."""
        return self.active_sessions.get(session_id)
    
    def delete_session(self, session_id: str):
        """Remove completed session."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
    
    def get_active_count(self) -> int:
        """Get count of active download sessions."""
        return len(self.active_sessions)


# Global singleton instance
playlist_download_service = PlaylistDownloadService()
