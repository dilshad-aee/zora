"""
YouTube Service - Search and video info extraction.
"""

import yt_dlp
from app.utils import format_duration


class YouTubeService:
    """Handles YouTube search and video info extraction."""
    
    @staticmethod
    def search(query: str, limit: int = 10) -> list:
        """
        Search YouTube for videos.
        
        Args:
            query: Search query
            limit: Max results
            
        Returns:
            List of search results
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': f'ytsearch{limit}',
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                
                if not results or 'entries' not in results:
                    return []
                
                formatted = []
                for entry in results['entries']:
                    if entry:
                        formatted.append({
                            'id': entry.get('id'),
                            'title': entry.get('title'),
                            'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                            'thumbnail': entry.get('thumbnail') or f"https://i.ytimg.com/vi/{entry.get('id')}/mqdefault.jpg",
                            'duration': entry.get('duration'),
                            'duration_str': format_duration(entry.get('duration', 0)),
                            'uploader': entry.get('uploader') or entry.get('channel'),
                            'view_count': entry.get('view_count', 0),
                        })
                
                return formatted
                
        except Exception as e:
            raise Exception(f"Search failed: {str(e)}")
    
    @staticmethod
    def get_info(url: str) -> dict:
        """
        Get video/playlist information.
        
        Args:
            url: YouTube URL
            
        Returns:
            Video info dictionary
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                result = {
                    'id': info.get('id'),
                    'title': info.get('title', 'Unknown'),
                    'thumbnail': info.get('thumbnail'),
                    'duration': info.get('duration'),
                    'duration_str': format_duration(info.get('duration', 0)),
                    'uploader': info.get('uploader') or info.get('artist', 'Unknown'),
                    'is_playlist': 'entries' in info,
                    'view_count': info.get('view_count', 0),
                    'upload_date': info.get('upload_date', ''),
                }
                
                if 'entries' in info:
                    entries = info.get('entries', [])
                    result['track_count'] = len(entries)
                    result['tracks'] = [
                        {
                            'title': e.get('title', 'Unknown'),
                            'duration': format_duration(e.get('duration', 0))
                        }
                        for e in entries[:10] if e
                    ]
                
                return result
                
        except Exception as e:
            raise Exception(f"Failed to get info: {str(e)}")
    
    @staticmethod
    def get_playlist_items(url: str) -> dict:
        """
        Extract playlist items without downloading.
        
        Args:
            url: Playlist URL
            
        Returns:
            Dictionary with playlist title and list of entries
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Don't download, just extract metadata
            'skip_download': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Format entries with all needed info
                entries = []
                for entry in info.get('entries', []):
                    if entry:
                        video_id = entry.get('id')
                        entries.append({
                            'id': video_id,
                            'title': entry.get('title', 'Unknown'),
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'thumbnail': entry.get('thumbnail') or f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
                            'duration': entry.get('duration', 0),
                            'duration_str': format_duration(entry.get('duration', 0)),
                            'uploader': entry.get('uploader') or entry.get('channel', 'Unknown'),
                        })
                
                return {
                    'title': info.get('title', 'Unknown Playlist'),
                    'playlist_count': len(entries),
                    'entries': entries
                }
                
        except Exception as e:
            raise Exception(f"Failed to get playlist items: {str(e)}")
