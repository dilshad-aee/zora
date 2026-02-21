"""
YouTube Service - Search and video info extraction.
"""

import os

import yt_dlp
from app.utils import format_duration, extract_playlist_id


class YouTubeService:
    """Handles YouTube search and video info extraction."""

    @staticmethod
    def _playlist_preview_limit() -> int:
        """Resolve safe upper bound for playlist preview extraction."""
        from app.models import Settings

        raw = None

        # 1) Admin setting from DB (preferred for runtime tuning)
        try:
            db_value = Settings.get('playlist_preview_limit', '')
            if str(db_value).strip():
                raw = db_value
        except Exception:
            raw = None

        # 2) Environment fallback
        if raw is None:
            raw = os.getenv(
                'ZORA_PLAYLIST_PREVIEW_LIMIT',
                str(Settings.DEFAULT_PREVIEW_LIMIT),
            )

        return Settings.normalize_preview_limit(raw)
    
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
                
                # Get video ID
                video_id = info.get('id')
                
                # Get thumbnail with multiple fallbacks
                thumbnail = info.get('thumbnail')
                if not thumbnail and info.get('thumbnails'):
                    thumbnails = info.get('thumbnails', [])
                    if thumbnails:
                        thumbnail = thumbnails[-1].get('url')
                if not thumbnail and video_id:
                    thumbnail = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
                
                result = {
                    'id': video_id,
                    'title': info.get('title', 'Unknown'),
                    'thumbnail': thumbnail,
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
        preview_limit = YouTubeService._playlist_preview_limit()
        playlist_id = extract_playlist_id(url)

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Don't download, just extract metadata
            'skip_download': True,
            # Prevent huge Mix/playlist extraction from overwhelming Termux.
            'playlist_items': f'1:{preview_limit}',
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Format entries with all needed info
                entries = []
                for entry in info.get('entries', []):
                    if entry:
                        video_id = entry.get('id')
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        entries.append({
                            'id': video_id,
                            'title': entry.get('title', 'Unknown'),
                            'url': video_url,
                            'thumbnail': entry.get('thumbnail') or f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
                            'duration': entry.get('duration', 0),
                            'duration_str': format_duration(entry.get('duration', 0)),
                            'uploader': entry.get('uploader') or entry.get('channel', 'Unknown'),
                        })

                return {
                    'title': info.get('title', 'Unknown Playlist'),
                    'playlist_count': len(entries),
                    'loaded_count': len(entries),
                    'preview_limit': preview_limit,
                    'is_limited': len(entries) >= preview_limit,
                    'playlist_id': playlist_id,
                    'is_mix': bool(playlist_id and playlist_id.upper().startswith('RD')),
                    'entries': entries
                }
                
        except Exception as e:
            raise Exception(f"Failed to get playlist items: {str(e)}")
