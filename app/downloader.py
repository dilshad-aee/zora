"""
Core YouTube Music downloader using yt-dlp.

Features:
- Highest quality audio extraction (320kbps)
- Playlist support with error isolation
- Robust error handling with retries
- Progress tracking with callbacks
"""

import os
import shutil
import glob
from pathlib import Path
from typing import Callable, Optional, List
import yt_dlp

from .utils import is_valid_url, is_playlist, sanitize_filename, ensure_dir
from .exceptions import DownloadError, PlaylistError, FFmpegError, InvalidURLError, NetworkError
from .logger import DownloadLogger, ProgressTracker


class YTMusicDownloader:
    """
    YouTube Music downloader with highest quality audio extraction.
    
    Usage:
        downloader = YTMusicDownloader(output_dir='./downloads')
        result = downloader.download('https://youtube.com/watch?v=...')
    """
    
    # Default options for highest quality
    DEFAULT_FORMAT = 'm4a'
    DEFAULT_QUALITY = '320'
    
    def __init__(
        self,
        output_dir: str = './downloads',
        audio_format: str = None,
        quality: str = None,
        on_progress: Optional[Callable[[dict], None]] = None,
        on_complete: Optional[Callable[[dict], None]] = None,
        on_message: Optional[Callable[[str, str], None]] = None,
        quiet: bool = False
    ):
        """
        Initialize downloader.
        
        Args:
            output_dir: Directory to save downloads
            audio_format: Output format (m4a, mp3, opus, flac, wav)
            quality: Audio quality (0-10 for VBR, or bitrate like '320')
            on_progress: Callback for progress updates
            on_complete: Callback when a file completes
            on_message: Callback for log messages
            quiet: Suppress console output
        """
        self.output_dir = ensure_dir(output_dir)
        self.audio_format = audio_format or self.DEFAULT_FORMAT
        self.quality = quality or self.DEFAULT_QUALITY
        self.quiet = quiet
        
        # Set up logger and progress tracker
        self.logger = DownloadLogger(on_message=on_message, quiet=quiet)
        self.progress_tracker = ProgressTracker(
            on_progress=on_progress,
            on_complete=on_complete
        )
        
        # Check FFmpeg
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """Check if FFmpeg is available."""
        if not shutil.which('ffmpeg'):
            raise FFmpegError()

    def _audio_extension_priority(self) -> List[str]:
        """Return preferred audio extensions in selection order."""
        preferred = [
            str(self.audio_format or '').lower().lstrip('.'),
            'm4a',
            'mp3',
            'aac',
            'ogg',
            'opus',
            'flac',
            'wav',
            'webm',
            'mka',
        ]
        result = []
        seen = set()
        for ext in preferred:
            if not ext or ext in seen:
                continue
            seen.add(ext)
            result.append(ext)
        return result

    def _resolve_final_audio_path(self, info: dict, ydl: yt_dlp.YoutubeDL) -> Optional[str]:
        """
        Resolve the final post-processed audio filepath on disk.

        yt-dlp progress hooks report the pre-conversion filename (often .webm).
        This resolver finds the actual converted file (e.g. .m4a).
        """
        extension_priority = self._audio_extension_priority()
        allowed_extensions = set(extension_priority)
        candidates = []

        try:
            prepared = ydl.prepare_filename(info)
            base = os.path.splitext(prepared)[0]
            for ext in extension_priority:
                candidates.append(f"{base}.{ext}")
            candidates.append(prepared)
        except Exception:
            pass

        video_id = info.get('id')
        if video_id:
            pattern = os.path.join(self.output_dir, f"* [{video_id}].*")
            candidates.extend(glob.glob(pattern))

        seen = set()
        existing_audio_files = []
        for candidate in candidates:
            abs_path = os.path.abspath(candidate)
            if abs_path in seen:
                continue
            seen.add(abs_path)

            if not os.path.isfile(abs_path):
                continue

            ext = os.path.splitext(abs_path)[1].lower().lstrip('.')
            if ext in allowed_extensions:
                existing_audio_files.append(abs_path)

        if not existing_audio_files:
            return None

        def rank(path: str) -> int:
            ext = os.path.splitext(path)[1].lower().lstrip('.')
            try:
                return extension_priority.index(ext)
            except ValueError:
                return len(extension_priority)

        existing_audio_files.sort(key=rank)
        return existing_audio_files[0]
    
    def _get_ydl_opts(self, playlist_mode: bool = False) -> dict:
        """
        Get yt-dlp options configured for highest quality.
        
        Args:
            playlist_mode: If True, configure for playlist download
            
        Returns:
            yt-dlp options dictionary
        """
        opts = {
            # Format selection: best audio quality
            'format': 'bestaudio/best',
            
            # Output template with sanitized filename and video ID for thumbnail matching
            'outtmpl': os.path.join(
                self.output_dir,
                '%(title).200s [%(id)s].%(ext)s'
            ),
            
            # Post-processing for audio extraction
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.audio_format,
                    'preferredquality': self.quality,
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                },
            ],
            
            # Download thumbnail for embedding
            'writethumbnail': True,
            
            # Retry settings for reliability
            'retries': 10,
            'fragment_retries': 10,
            'socket_timeout': 30,
            
            # Logger and progress
            'logger': self.logger,
            'progress_hooks': [self.progress_tracker.hook],
            
            # Other settings
            'quiet': True,
            'no_warnings': self.quiet,
            'extract_flat': False,
            
            # Geo-bypass for better compatibility
            'geo_bypass': True,
        }
        
        # Playlist-specific options
        if playlist_mode:
            opts['ignoreerrors'] = True  # Continue on individual errors
            opts['extract_flat'] = False
        else:
            opts['noplaylist'] = True  # Download single video only
            
        # Add local thumbnail saving hook
        opts['progress_hooks'].append(self._save_thumbnail_hook)
        
        return opts

    def _save_thumbnail_hook(self, d):
        """Hook to save thumbnail before it gets embedded/deleted."""
        if d['status'] == 'finished':
            try:
                # Get the downloaded filename (e.g. Song.m4a)
                filename = d.get('filename')
                if not filename:
                    return
                
                # Get info dict for ID
                info = d.get('info_dict', {})
                video_id = info.get('id')
                
                # Check for potential thumbnail files
                base_path = os.path.splitext(filename)[0]
                
                # Common thumbnail extensions
                for ext in ['.webp', '.jpg', '.png', '.jpeg']:
                    thumb_path = f"{base_path}{ext}"
                    if os.path.exists(thumb_path):
                        # Found the thumbnail!
                        
                        # Determine target name (prefer video_id, fallback to safe filename)
                        if video_id:
                            target_name = f"{video_id}{ext}"
                        else:
                            target_name = f"local_{os.path.basename(thumb_path)}"

                        thumbnails_dir = Path(self.output_dir) / 'thumbnails'
                        thumbnails_dir.mkdir(parents=True, exist_ok=True)
                        target_path = thumbnails_dir / target_name
                        
                        # Copy it (copy instead of move in case EmbedThumbnail needs it)
                        shutil.copy2(thumb_path, target_path)
                        
                        # Store in d for later use if needed (though d is local to hook)
                        # We rely on the DB update step to find this file based on ID
                        break
                        
            except Exception as e:
                # Don't fail the download just because thumbnail copy failed
                if not self.quiet:
                    print(f"Warning: Failed to save thumbnail: {e}")
    
    def get_info(self, url: str) -> dict:
        """
        Get video/playlist info without downloading.
        
        Args:
            url: YouTube URL
            
        Returns:
            Info dictionary with title, duration, thumbnail, etc.
        """
        if not is_valid_url(url):
            raise InvalidURLError(url)
        
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist' if is_playlist(url) else False,
        }
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return ydl.sanitize_info(info)
        except yt_dlp.DownloadError as e:
            raise DownloadError(str(e), url)
    
    def download(self, url: str) -> dict:
        """
        Download audio from URL (auto-detects playlist).
        
        Args:
            url: YouTube or YouTube Music URL
            
        Returns:
            Result dictionary with success status, title, etc.
        """
        if not is_valid_url(url):
            raise InvalidURLError(url)
        
        if is_playlist(url):
            return self.download_playlist(url)
        else:
            return self.download_single(url)
    
    def download_single(self, url: str) -> dict:
        """
        Download single video as audio.
        
        Args:
            url: YouTube URL
            
        Returns:
            Result dictionary
        """
        if not is_valid_url(url):
            raise InvalidURLError(url)
        
        opts = self._get_ydl_opts(playlist_mode=False)
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if info:
                    final_filename = self._resolve_final_audio_path(info, ydl)
                    if not final_filename:
                        final_filename = ydl.prepare_filename(info)
                        if self.audio_format and not final_filename.endswith(f".{self.audio_format}"):
                            base = os.path.splitext(final_filename)[0]
                            final_filename = f"{base}.{self.audio_format}"

                    return {
                        'success': True,
                        'type': 'single',
                        'title': info.get('title'),
                        'artist': info.get('artist') or info.get('uploader'),
                        'duration': info.get('duration'),
                        'thumbnail': info.get('thumbnail'),
                        'filename': final_filename,
                        'url': url,
                        'output_dir': self.output_dir,
                    }
                else:
                    return {
                        'success': False,
                        'type': 'single',
                        'error': 'No info returned',
                        'url': url,
                    }
                    
        except yt_dlp.DownloadError as e:
            error_msg = str(e)
            
            # Categorize error
            if '403' in error_msg:
                raise NetworkError(
                    "Access forbidden (HTTP 403). Try using browser cookies.",
                    retry_count=0
                )
            elif '429' in error_msg:
                raise NetworkError(
                    "Too many requests (HTTP 429). Please wait and try again.",
                    retry_count=0
                )
            else:
                raise DownloadError(error_msg, url)
                
        except Exception as e:
            raise DownloadError(f"Unexpected error: {e}", url)
    
    def download_playlist(self, url: str) -> dict:
        """
        Download all videos from playlist.
        
        Args:
            url: Playlist URL
            
        Returns:
            Result dictionary with success/failed counts
        """
        if not is_valid_url(url):
            raise InvalidURLError(url)
        
        opts = self._get_ydl_opts(playlist_mode=True)
        
        downloaded = []
        failed = []
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if info:
                    playlist_title = info.get('title', 'Unknown Playlist')
                    entries = info.get('entries', [])
                    
                    for entry in entries:
                        if entry:
                            downloaded.append({
                                'title': entry.get('title'),
                                'id': entry.get('id'),
                            })
                        else:
                            # Entry is None = download failed but continued
                            failed.append({'error': 'Failed to download'})
                    
                    return {
                        'success': True,
                        'type': 'playlist',
                        'playlist_title': playlist_title,
                        'total': len(entries),
                        'downloaded': len(downloaded),
                        'failed': len(failed),
                        'items': downloaded,
                        'failed_items': failed,
                        'output_dir': self.output_dir,
                    }
                    
        except yt_dlp.DownloadError as e:
            raise PlaylistError(str(e), playlist_url=url, failed_items=failed)
            
        except Exception as e:
            raise PlaylistError(f"Unexpected error: {e}", playlist_url=url)
        
        return {
            'success': False,
            'type': 'playlist',
            'error': 'Unknown error',
            'url': url,
        }


# Convenience function for simple usage
def download_audio(
    url: str,
    output_dir: str = './downloads',
    audio_format: str = 'm4a',
    quality: str = '320',
    on_progress: Optional[Callable[[dict], None]] = None
) -> dict:
    """
    Simple function to download audio from YouTube URL.
    
    Args:
        url: YouTube or YouTube Music URL
        output_dir: Directory to save files
        audio_format: Output format (m4a, mp3, etc.)
        quality: Audio quality/bitrate
        on_progress: Progress callback
        
    Returns:
        Result dictionary
    """
    downloader = YTMusicDownloader(
        output_dir=output_dir,
        audio_format=audio_format,
        quality=quality,
        on_progress=on_progress
    )
    return downloader.download(url)
