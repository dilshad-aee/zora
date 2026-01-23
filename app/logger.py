"""Custom logger for yt-dlp with progress callbacks."""

from typing import Callable, Optional


class DownloadLogger:
    """
    Custom logger for yt-dlp that supports callbacks.
    
    Usage:
        logger = DownloadLogger(on_message=my_callback)
        ydl_opts = {'logger': logger}
    """
    
    def __init__(
        self,
        on_message: Optional[Callable[[str, str], None]] = None,
        quiet: bool = False
    ):
        """
        Initialize logger.
        
        Args:
            on_message: Callback function(level, message)
            quiet: If True, suppress console output
        """
        self.on_message = on_message
        self.quiet = quiet
    
    def debug(self, msg: str):
        """Handle debug messages."""
        # yt-dlp sends info messages through debug with no prefix
        if msg.startswith('[debug] '):
            return  # Skip actual debug messages
        self.info(msg)
    
    def info(self, msg: str):
        """Handle info messages."""
        if self.on_message:
            self.on_message('info', msg)
        if not self.quiet:
            print(f"[INFO] {msg}")
    
    def warning(self, msg: str):
        """Handle warning messages."""
        if self.on_message:
            self.on_message('warning', msg)
        if not self.quiet:
            print(f"[WARNING] {msg}")
    
    def error(self, msg: str):
        """Handle error messages."""
        if self.on_message:
            self.on_message('error', msg)
        # Always print errors
        print(f"[ERROR] {msg}")


class ProgressTracker:
    """
    Track download progress with callback support.
    
    Usage:
        tracker = ProgressTracker(on_progress=my_callback)
        ydl_opts = {'progress_hooks': [tracker.hook]}
    """
    
    def __init__(
        self,
        on_progress: Optional[Callable[[dict], None]] = None,
        on_complete: Optional[Callable[[dict], None]] = None
    ):
        """
        Initialize progress tracker.
        
        Args:
            on_progress: Called during download with progress dict
            on_complete: Called when download finishes
        """
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.current_file = None
    
    def hook(self, d: dict):
        """
        Progress hook for yt-dlp.
        
        Args:
            d: Progress dictionary from yt-dlp
        """
        status = d.get('status')
        
        if status == 'downloading':
            self.current_file = d.get('filename', '')
            
            progress_info = {
                'status': 'downloading',
                'filename': self.current_file,
                'downloaded_bytes': d.get('downloaded_bytes', 0),
                'total_bytes': d.get('total_bytes') or d.get('total_bytes_estimate', 0),
                'speed': d.get('speed', 0),
                'eta': d.get('eta', 0),
                'percent_str': d.get('_percent_str', '0%'),
                'percent': self._parse_percent(d.get('_percent_str', '0%')),
            }
            
            if self.on_progress:
                self.on_progress(progress_info)
                
        elif status == 'finished':
            complete_info = {
                'status': 'finished',
                'filename': d.get('filename', self.current_file),
                'total_bytes': d.get('total_bytes', 0),
            }
            
            if self.on_complete:
                self.on_complete(complete_info)
    
    def _parse_percent(self, percent_str: str) -> float:
        """Parse percentage string to float."""
        try:
            if not percent_str:
                return 0.0
            
            # Remove ANSI color codes
            import re
            clean = re.sub(r'\x1b\[[0-9;]*m', '', str(percent_str))
            
            # Clean up string
            clean = clean.strip().rstrip('%')
            
            return float(clean)
        except (ValueError, AttributeError, TypeError):
            return 0.0
