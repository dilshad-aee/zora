"""
Download model for storing download history.
"""

import os
import re
from datetime import datetime
from .database import db


class Download(db.Model):
    """Represents a downloaded track."""
    
    __tablename__ = 'downloads'
    
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(20), index=True)
    title = db.Column(db.String(500), nullable=False)
    artist = db.Column(db.String(200))
    filename = db.Column(db.String(500))
    format = db.Column(db.String(10), default='m4a')
    quality = db.Column(db.String(10), default='320kbps')
    thumbnail = db.Column(db.String(500))
    duration = db.Column(db.Integer, default=0)
    file_size = db.Column(db.Integer, default=0)
    downloaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary for JSON response."""
        from config import config
        
        # Generate thumbnail using local file if available, else remote
        thumbnail = None
        real_video_id = self._extract_video_id()
        
        # Try to find a local thumbnail
        if real_video_id:
            for ext in ['.webp', '.jpg', '.png', '.jpeg']:
                thumb_name = f"{real_video_id}{ext}"
                if (config.THUMBNAILS_DIR / thumb_name).exists():
                    thumbnail = f"/api/thumbnails/{thumb_name}"
                    break
        
        # Use stored thumbnail URL if no local file found
        if not thumbnail and self.thumbnail:
            thumbnail = self.thumbnail
        
        # Final fallback to YouTube thumbnail if we have a real video ID
        if not thumbnail and real_video_id:
            thumbnail = f"https://i.ytimg.com/vi/{real_video_id}/mqdefault.jpg"
        
        return {
            'id': self.id,
            'video_id': self.video_id,
            'title': self.title,
            'artist': self.artist,
            'uploader': self.artist,
            'filename': self.filename,
            'format': self.format,
            'quality': self.quality,
            'thumbnail': thumbnail,
            'duration': self.duration,
            'file_size': self.file_size,
            'downloaded_at': self.downloaded_at.isoformat() if self.downloaded_at else None,
            'completed_at': self.downloaded_at.isoformat() if self.downloaded_at else None,
        }
    
    def _extract_video_id(self):
        """Extract real YouTube video ID from video_id or filename."""
        from config import config
        
        # If video_id is a real YouTube ID (not local_*), use it
        if self.video_id and not self.video_id.startswith('local_'):
            return self.video_id
        
        # Try to extract from filename pattern: "Title [videoId].ext"
        if self.filename:
            match = re.search(r'\[([a-zA-Z0-9_-]{11})\]', self.filename)
            if match:
                return match.group(1)
        
        # Fallback: Try to match by file timestamp with thumbnail files
        if self.filename and config.THUMBNAILS_DIR.exists():
            try:
                audio_path = config.DOWNLOAD_DIR / self.filename
                if audio_path.exists():
                    audio_mtime = audio_path.stat().st_mtime
                    # Look for thumbnail with matching timestamp (within 5 seconds)
                    for thumb_file in config.THUMBNAILS_DIR.iterdir():
                        if thumb_file.is_file() and thumb_file.suffix.lower() in ['.webp', '.jpg', '.png', '.jpeg']:
                            thumb_mtime = thumb_file.stat().st_mtime
                            if abs(audio_mtime - thumb_mtime) < 5:
                                # Found matching thumbnail by timestamp
                                return thumb_file.stem
            except Exception:
                pass
        
        return None
    
    @classmethod
    def get_history(cls, limit=100):
        """Get download history with auto-sync from filesystem."""
        from config import config
        
        # 1. Get all known files from DB
        db_records = cls.query.all()
        db_files = {d.filename: d for d in db_records if d.filename}
        
        # 2. Get all actual files from disk
        disk_files = []
        if config.DOWNLOAD_DIR.exists():
            for f in config.DOWNLOAD_DIR.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    disk_files.append(f.name)
        
        # 3. Process Sync
        
        # A. Remove DB records for files that no longer exist on disk
        for filename, record in db_files.items():
            if filename not in disk_files:
                db.session.delete(record)
        
        # B. Add new files to DB (files on disk but not in DB)
        for filename in disk_files:
            if filename not in db_files:
                # Create record for new file
                title = filename
                artist = 'Unknown Artist'
                thumbnail = ''
                video_id = ''
                
                # Parse filename: "Artist - Title.ext" or just "Title.ext"
                stem = os.path.splitext(filename)[0]
                if ' - ' in stem:
                    parts = stem.split(' - ', 1)
                    artist = parts[0]
                    title = parts[1]
                else:
                    title = stem
                
                # Try to extract YouTube video ID from filename (11 chars pattern)
                yt_id_match = re.search(r'\[([a-zA-Z0-9_-]{11})\]', filename)
                if yt_id_match:
                    video_id = yt_id_match.group(1)
                    # Check for local thumbnail first
                    for ext in ['.webp', '.jpg', '.png', '.jpeg']:
                        thumb_path = config.THUMBNAILS_DIR / f"{video_id}{ext}"
                        if thumb_path.exists():
                            thumbnail = f"/api/thumbnails/{video_id}{ext}"
                            break
                    else:
                        thumbnail = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
                else:
                    # Generate a local ID
                    video_id = f"local_{abs(hash(filename))}"[:20]
                
                # Get file stats
                filepath = config.DOWNLOAD_DIR / filename
                try:
                    stat = filepath.stat()
                    file_size = stat.st_size
                    downloaded_at = datetime.fromtimestamp(stat.st_mtime)
                except Exception:
                    file_size = 0
                    downloaded_at = datetime.utcnow()
                
                new_record = cls(
                    title=title,
                    artist=artist,
                    filename=filename,
                    file_size=file_size,
                    downloaded_at=downloaded_at,
                    video_id=video_id,
                    thumbnail=thumbnail
                )
                db.session.add(new_record)
        
        try:
            db.session.commit()
        except Exception as e:
            print(f"DB sync error: {e}")
            db.session.rollback()
        
        # 4. Return sorted list
        return cls.query.order_by(cls.downloaded_at.desc()).limit(limit).all()
    
    @classmethod
    def check_duplicate(cls, title, video_id=None):
        """Check if a download already exists AND the file is still there."""
        from config import config
        
        if video_id and not video_id.startswith('local_'):
            existing = cls.query.filter_by(video_id=video_id).first()
            if existing:
                # Check if file actually exists
                if existing.filename:
                    filepath = config.DOWNLOAD_DIR / existing.filename
                    if filepath.exists():
                        return True, existing.filename
                    else:
                        # File deleted, remove from DB
                        db.session.delete(existing)
                        db.session.commit()
                        return False, None
        
        # Also check by title
        if title:
            existing = cls.query.filter(
                cls.title.ilike(f"%{title}%")
            ).first()
            
            if existing:
                # Check if file actually exists
                if existing.filename:
                    filepath = config.DOWNLOAD_DIR / existing.filename
                    if filepath.exists():
                        return True, existing.filename
                    else:
                        # File deleted, remove from DB
                        db.session.delete(existing)
                        db.session.commit()
                        return False, None
        
        return False, None
    
    @classmethod
    def add(cls, **kwargs):
        """Add a new download record."""
        try:
            download = cls(**kwargs)
            db.session.add(download)
            db.session.commit()
            return download
        except Exception as e:
            print(f"Error adding download: {e}")
            db.session.rollback()
            return None
    
    @classmethod
    def update_thumbnail(cls, video_id, thumbnail):
        """Update thumbnail for existing record."""
        if not video_id or not thumbnail:
            return False
        
        record = cls.query.filter_by(video_id=video_id).first()
        if record:
            record.thumbnail = thumbnail
            db.session.commit()
            return True
        return False
    
    @classmethod
    def delete_by_id(cls, download_id):
        """Delete a download record by ID."""
        download = cls.query.get(download_id)
        if download:
            db.session.delete(download)
            db.session.commit()
            return True
        return False
    
    @classmethod
    def delete_by_filename(cls, filename):
        """Delete a download record by filename."""
        download = cls.query.filter_by(filename=filename).first()
        if download:
            db.session.delete(download)
            db.session.commit()
            return True
        return False
    
    @classmethod
    def clear_all(cls):
        """Clear all download history."""
        cls.query.delete()
        db.session.commit()
    
    @classmethod
    def get_by_video_id(cls, video_id):
        """Get download by video ID."""
        return cls.query.filter_by(video_id=video_id).first()
    
    @classmethod
    def get_by_filename(cls, filename):
        """Get download by filename."""
        return cls.query.filter_by(filename=filename).first()