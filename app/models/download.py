"""
Download model for storing download history.
"""

import os
import re
import threading
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

    # In-memory duplicate index for fast checks
    _dup_cache_lock = threading.Lock()
    _dup_cache = None
    _dup_cache_count = -1
    
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

    @staticmethod
    def _normalize_text(value):
        """Normalize free text for stable duplicate comparisons."""
        text = (value or '').lower()
        if not text:
            return ''

        # Remove bracketed segments often used for noisy metadata tags.
        text = re.sub(r'\([^)]*\)', ' ', text)
        text = re.sub(r'\[[^\]]*\]', ' ', text)
        text = re.sub(r'\{[^}]*\}', ' ', text)
        text = text.replace('&', ' and ')
        text = re.sub(r'[^a-z0-9\s]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @classmethod
    def _normalize_title(cls, title):
        return cls._normalize_text(title)

    @classmethod
    def _normalize_artist(cls, artist):
        return cls._normalize_text(artist)

    @classmethod
    def _duration_value(cls, duration):
        try:
            value = int(duration)
            return value if value > 0 else 0
        except Exception:
            return 0

    @classmethod
    def _duration_match(cls, left, right, tolerance=3):
        left_val = cls._duration_value(left)
        right_val = cls._duration_value(right)
        if left_val <= 0 or right_val <= 0:
            return False
        return abs(left_val - right_val) <= tolerance

    @classmethod
    def invalidate_duplicate_cache(cls):
        """Invalidate in-memory duplicate index."""
        with cls._dup_cache_lock:
            cls._dup_cache = None
            cls._dup_cache_count = -1

    @classmethod
    def _build_duplicate_cache(cls):
        records = cls.query.with_entities(
            cls.id,
            cls.video_id,
            cls.title,
            cls.artist,
            cls.filename,
            cls.duration,
        ).all()

        by_video_id = {}
        by_title = {}
        by_title_artist = {}

        for row in records:
            title_norm = cls._normalize_title(row.title)
            artist_norm = cls._normalize_artist(row.artist)
            duration_val = cls._duration_value(row.duration)

            entry = {
                'id': row.id,
                'video_id': row.video_id,
                'title_norm': title_norm,
                'artist_norm': artist_norm,
                'filename': row.filename,
                'duration': duration_val,
            }

            video_id = (row.video_id or '').strip()
            if video_id and not video_id.startswith('local_'):
                by_video_id.setdefault(video_id, []).append(entry)

            if title_norm:
                by_title.setdefault(title_norm, []).append(entry)
                if artist_norm:
                    by_title_artist.setdefault((title_norm, artist_norm), []).append(entry)

        return {
            'count': len(records),
            'by_video_id': by_video_id,
            'by_title': by_title,
            'by_title_artist': by_title_artist,
        }

    @classmethod
    def _ensure_duplicate_cache(cls):
        current_count = cls.query.count()
        with cls._dup_cache_lock:
            if cls._dup_cache is None or cls._dup_cache_count != current_count:
                cls._dup_cache = cls._build_duplicate_cache()
                cls._dup_cache_count = cls._dup_cache.get('count', current_count)
            return cls._dup_cache

    @classmethod
    def _delete_stale_records(cls, stale_ids):
        if not stale_ids:
            return
        cls.query.filter(cls.id.in_(list(stale_ids))).delete(synchronize_session=False)
        db.session.commit()
        cls.invalidate_duplicate_cache()

    @classmethod
    def _is_same_track(cls, entry, title_norm, artist_norm, duration, video_id):
        entry_video_id = (entry.get('video_id') or '').strip()
        if video_id and entry_video_id and video_id == entry_video_id:
            return True

        if not title_norm or title_norm != entry.get('title_norm'):
            return False

        entry_artist = entry.get('artist_norm') or ''
        artist_exact = bool(artist_norm and entry_artist and artist_norm == entry_artist)
        artist_missing = not artist_norm or not entry_artist
        duration_exact = cls._duration_match(duration, entry.get('duration'))
        duration_unknown = cls._duration_value(duration) <= 0 or cls._duration_value(entry.get('duration')) <= 0

        # Require multiple parameters to avoid false positives.
        if artist_exact and (duration_exact or duration_unknown):
            return True
        if artist_missing and duration_exact:
            return True
        return False
    
    @classmethod
    def get_history(cls, limit=100):
        """Get download history with auto-sync from filesystem."""
        from config import config
        changes_made = False
        
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
                changes_made = True
        
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
                changes_made = True
        
        try:
            db.session.commit()
            if changes_made:
                cls.invalidate_duplicate_cache()
        except Exception as e:
            print(f"DB sync error: {e}")
            db.session.rollback()
        
        # 4. Return sorted list
        return cls.query.order_by(cls.downloaded_at.desc()).limit(limit).all()
    
    @classmethod
    def check_duplicate(cls, title, video_id=None, artist=None, duration=None):
        """
        Fast multi-parameter duplicate check.

        Priority:
        1) Exact video_id match (indexed).
        2) Strict normalized title + artist + duration-tolerant match.
        """
        from config import config

        cache = cls._ensure_duplicate_cache()
        video_id = (video_id or '').strip()
        title_norm = cls._normalize_title(title)
        artist_norm = cls._normalize_artist(artist)
        duration_val = cls._duration_value(duration)

        candidates = []
        if video_id and not video_id.startswith('local_'):
            candidates.extend(cache.get('by_video_id', {}).get(video_id, []))

        if title_norm:
            if artist_norm:
                candidates.extend(cache.get('by_title_artist', {}).get((title_norm, artist_norm), []))
            candidates.extend(cache.get('by_title', {}).get(title_norm, []))

        if not candidates:
            return False, None

        seen_ids = set()
        stale_ids = set()

        for entry in candidates:
            entry_id = entry.get('id')
            if entry_id in seen_ids:
                continue
            seen_ids.add(entry_id)

            if not cls._is_same_track(entry, title_norm, artist_norm, duration_val, video_id):
                continue

            filename = entry.get('filename') or ''
            if not filename:
                continue

            filepath = config.DOWNLOAD_DIR / filename
            if filepath.exists():
                return True, filename

            stale_ids.add(entry_id)

        if stale_ids:
            cls._delete_stale_records(stale_ids)

        return False, None
    
    @classmethod
    def add(cls, **kwargs):
        """Add a new download record."""
        try:
            download = cls(**kwargs)
            db.session.add(download)
            db.session.commit()
            cls.invalidate_duplicate_cache()
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
            cls.invalidate_duplicate_cache()
            return True
        return False
    
    @classmethod
    def delete_by_filename(cls, filename):
        """Delete a download record by filename."""
        download = cls.query.filter_by(filename=filename).first()
        if download:
            db.session.delete(download)
            db.session.commit()
            cls.invalidate_duplicate_cache()
            return True
        return False
    
    @classmethod
    def clear_all(cls):
        """Clear all download history."""
        cls.query.delete()
        db.session.commit()
        cls.invalidate_duplicate_cache()
    
    @classmethod
    def get_by_video_id(cls, video_id):
        """Get download by video ID."""
        return cls.query.filter_by(video_id=video_id).first()
    
    @classmethod
    def get_by_filename(cls, filename):
        """Get download by filename."""
        return cls.query.filter_by(filename=filename).first()
