"""Custom exceptions for YouTube Music downloader."""


class DownloadError(Exception):
    """General download failure."""
    
    def __init__(self, message: str, url: str = None):
        self.url = url
        super().__init__(message)


class PlaylistError(Exception):
    """Playlist-specific errors."""
    
    def __init__(self, message: str, playlist_url: str = None, failed_items: list = None):
        self.playlist_url = playlist_url
        self.failed_items = failed_items or []
        super().__init__(message)


class FFmpegError(Exception):
    """FFmpeg not found or failed."""
    
    def __init__(self, message: str = None):
        default_msg = (
            "FFmpeg not found. Please install FFmpeg:\n"
            "  macOS: brew install ffmpeg\n"
            "  Ubuntu: sudo apt install ffmpeg\n"
            "  Windows: choco install ffmpeg"
        )
        super().__init__(message or default_msg)


class NetworkError(Exception):
    """Network connection issues."""
    
    def __init__(self, message: str, retry_count: int = 0):
        self.retry_count = retry_count
        super().__init__(message)


class InvalidURLError(Exception):
    """Invalid or unsupported URL."""
    
    def __init__(self, url: str):
        self.url = url
        super().__init__(f"Invalid or unsupported URL: {url}")
