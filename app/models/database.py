"""
Database initialization and SQLAlchemy instance.
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def init_db(app):
    """Initialize database with Flask app."""
    db.init_app(app)
    
    with app.app_context():
        # Import models to register them
        from . import download, settings, playlist
        
        # Create all tables
        db.create_all()


def migrate_from_json(app, json_path):
    """Migrate existing history.json to SQLite."""
    import json
    from pathlib import Path
    from .download import Download
    
    json_file = Path(json_path)
    if not json_file.exists():
        return
    
    with app.app_context():
        try:
            with open(json_file, 'r') as f:
                history = json.load(f)
            
            for item in history:
                # Check if already exists
                existing = Download.query.filter_by(
                    title=item.get('title')
                ).first()
                
                if not existing:
                    download = Download(
                        video_id=item.get('video_id', ''),
                        title=item.get('title', 'Unknown'),
                        artist=item.get('uploader', 'Unknown'),
                        filename=item.get('filename', ''),
                        format=item.get('format', 'm4a'),
                        quality=item.get('quality', '320kbps'),
                        thumbnail=item.get('thumbnail', ''),
                        duration=item.get('duration', 0),
                        file_size=item.get('file_size', 0),
                    )
                    db.session.add(download)
            
            db.session.commit()
            print(f"Migrated {len(history)} items from history.json")
            
        except Exception as e:
            print(f"Migration error: {e}")
            db.session.rollback()
