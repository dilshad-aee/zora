"""
Download model for storing download history.
"""

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
        return {
            'id': self.id,
            'video_id': self.video_id,
            'title': self.title,
            'uploader': self.artist,
            'filename': self.filename,
            'format': self.format,
            'quality': self.quality,
            'thumbnail': self.thumbnail,
            'duration': self.duration,
            'file_size': self.file_size,
            'completed_at': self.downloaded_at.isoformat() if self.downloaded_at else None,
        }
    
    @classmethod
    def get_history(cls, limit=100):
        """Get download history with auto-sync from filesystem."""
        from config import config
        import os
        
        # 1. Get all known files from DB
        db_files = {d.filename: d for d in cls.query.all() if d.filename}
        
        # 2. Get all actual files from disk
        disk_files = []
        if config.DOWNLOAD_DIR.exists():
            for f in config.DOWNLOAD_DIR.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    disk_files.append(f.name)
        
        # 3. Process Sync
        
        # A. Remove missing files from DB
        for filename, record in db_files.items():
            if filename not in disk_files:
                db.session.delete(record)
        
        # B. Add new files to DB
        for filename in disk_files:
            if filename not in db_files:
                # Create record for new file
                # Try to parse Artist - Title from filename if possible
                title = filename
                artist = 'Unknown Artist'
                
                # Simple heuristic: "Artist - Title.ext"
                stem = os.path.splitext(filename)[0]
                if ' - ' in stem:
                    parts = stem.split(' - ', 1)
                    artist = parts[0]
                    title = parts[1]
                else:
                    title = stem
                
                # Get file stats
                filepath = config.DOWNLOAD_DIR / filename
                stat = filepath.stat()
                
                new_record = cls(
                    title=title,
                    artist=artist,
                    filename=filename,
                    file_size=stat.st_size,
                    downloaded_at=datetime.fromtimestamp(stat.st_mtime),
                    video_id=f"local_{abs(hash(filename))}"[:20]  # Fake ID for local files
                )
                db.session.add(new_record)
        
        db.session.commit()
        
        # 4. Return sorted list
        return cls.query.order_by(cls.downloaded_at.desc()).limit(limit).all()
    
    @classmethod
    def check_duplicate(cls, title, video_id=None):
        """Check if a download already exists AND the file is still there."""
        from config import config
        
        if video_id:
            existing = cls.query.filter_by(video_id=video_id).first()
            if existing:
                # Check if file actually exists
                if existing.filename:
                    filepath = config.DOWNLOAD_DIR / existing.filename
                    if filepath.exists():
                        return True, existing.filename
                    else:
                        # File deleted, remove from DB
                        from .database import db
                        db.session.delete(existing)
                        db.session.commit()
                        return False, None
        
        # Also check by title
        existing = cls.query.filter(
            cls.title.ilike(title)
        ).first()
        
        if existing:
            # Check if file actually exists
            if existing.filename:
                filepath = config.DOWNLOAD_DIR / existing.filename
                if filepath.exists():
                    return True, existing.filename
                else:
                    # File deleted, remove from DB
                    from .database import db
                    db.session.delete(existing)
                    db.session.commit()
                    return False, None
        
        return False, None
    
    @classmethod
    def add(cls, **kwargs):
        """Add a new download record."""
        download = cls(**kwargs)
        db.session.add(download)
        db.session.commit()
        return download
    
    @classmethod
    def clear_all(cls):
        """Clear all download history."""
        cls.query.delete()
        db.session.commit()
