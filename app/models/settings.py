"""
Settings model for persisting user preferences.
"""

from .database import db


class Settings(db.Model):
    """User settings stored in database."""
    
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(500))
    
    # Default settings
    DEFAULTS = {
        'default_format': 'm4a',
        'default_quality': '320',
        'check_duplicates': 'true',
        'skip_duplicates': 'true',
        'theme': 'dark',
        'download_dir': '',
    }
    
    @classmethod
    def get(cls, key, default=None):
        """Get a setting value."""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            return setting.value
        return default or cls.DEFAULTS.get(key)
    
    @classmethod
    def set(cls, key, value):
        """Set a setting value."""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
        else:
            setting = cls(key=key, value=str(value))
            db.session.add(setting)
        db.session.commit()
        return setting
    
    @classmethod
    def get_all(cls):
        """Get all settings as dictionary."""
        settings = {}
        for key, default in cls.DEFAULTS.items():
            settings[key] = cls.get(key, default)
        
        # Convert string booleans
        if settings.get('check_duplicates') in ['true', 'True', '1']:
            settings['check_duplicates'] = True
        else:
            settings['check_duplicates'] = False

        if settings.get('skip_duplicates') in ['true', 'True', '1']:
            settings['skip_duplicates'] = True
        else:
            settings['skip_duplicates'] = False

        settings['download_dir'] = str(settings.get('download_dir') or '').strip()
        
        return settings
    
    @classmethod
    def update_all(cls, data):
        """Update multiple settings at once."""
        for key, value in data.items():
            if key in cls.DEFAULTS:
                cls.set(key, value)
        return cls.get_all()
