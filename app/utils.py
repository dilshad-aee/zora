"""Utility functions for YouTube Music downloader."""

import re
import os


# Supported URL patterns
YOUTUBE_PATTERNS = [
    r'^https?://(www\.)?youtube\.com/watch\?v=[\w-]+',
    r'^https?://(www\.)?youtube\.com/playlist\?list=[\w-]+',
    r'^https?://youtu\.be/[\w-]+',
    r'^https?://music\.youtube\.com/watch\?v=[\w-]+',
    r'^https?://music\.youtube\.com/playlist\?list=[\w-]+',
]

PLAYLIST_PATTERNS = [
    r'^https?://(www\.)?youtube\.com/playlist\?list=[\w-]+',
    r'^https?://music\.youtube\.com/playlist\?list=[\w-]+',
    r'[?&]list=[\w-]+',  # Any URL with list parameter
]


def is_valid_url(url: str) -> bool:
    """
    Check if URL is a valid YouTube or YouTube Music URL.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid YouTube/YT Music URL
    """
    if not url or not isinstance(url, str):
        return False
    
    url = url.strip()
    return any(re.match(pattern, url) for pattern in YOUTUBE_PATTERNS)


def is_playlist(url: str) -> bool:
    """
    Check if URL is a playlist URL.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is a playlist
    """
    if not url or not isinstance(url, str):
        return False
    
    url = url.strip()
    return any(re.search(pattern, url) for pattern in PLAYLIST_PATTERNS)


def sanitize_filename(title: str, max_length: int = 200) -> str:
    """
    Clean filename by removing/replacing invalid characters.
    
    Args:
        title: Original title
        max_length: Maximum filename length
        
    Returns:
        Sanitized filename safe for all OS
    """
    if not title:
        return "untitled"
    
    # Characters not allowed in filenames
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, '_', title)
    
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(' .')
    
    # Truncate if too long (leave room for extension)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized or "untitled"


def format_duration(seconds) -> str:
    """
    Convert seconds to human-readable duration.
    
    Args:
        seconds: Duration in seconds (int or float)
        
    Returns:
        Formatted string like "3:45" or "1:23:45"
    """
    if seconds is None or seconds < 0:
        return "0:00"
    
    # Convert to int to handle floats
    seconds = int(seconds)
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_filesize(bytes_size: int) -> str:
    """
    Convert bytes to human-readable size.
    
    Args:
        bytes_size: Size in bytes
        
    Returns:
        Formatted string like "5.2 MB"
    """
    if bytes_size is None or bytes_size < 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    
    return f"{bytes_size:.1f} TB"


def ensure_dir(path: str) -> str:
    """
    Create directory if it doesn't exist.
    
    Args:
        path: Directory path
        
    Returns:
        Absolute path to directory
    """
    abs_path = os.path.abspath(path)
    os.makedirs(abs_path, exist_ok=True)
    return abs_path


def extract_video_id(url: str) -> str | None:
    """
    Extract video ID from YouTube URL.
    
    Args:
        url: YouTube URL
        
    Returns:
        Video ID or None
    """
    patterns = [
        r'(?:v=|/)([a-zA-Z0-9_-]{11})(?:[&?]|$)',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None
