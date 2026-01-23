"""
Configuration Module for YT Music Downloader.
Centralizes all app settings with environment variable support.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Application configuration with sensible defaults."""
    
    # Paths
    BASE_DIR = Path(__file__).parent.parent
    DOWNLOAD_DIR = BASE_DIR / 'downloads'
    DATABASE_PATH = BASE_DIR / 'data.db'
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24).hex())
    DEBUG = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    
    # Database
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Download defaults
    DEFAULT_FORMAT = os.getenv('DEFAULT_FORMAT', 'm4a')
    DEFAULT_QUALITY = os.getenv('DEFAULT_QUALITY', '320')
    CHECK_DUPLICATES = os.getenv('CHECK_DUPLICATES', 'true').lower() == 'true'
    
    # Supported formats
    AUDIO_FORMATS = ['m4a', 'mp3', 'opus', 'flac', 'wav', 'ogg', 'aac']
    QUALITIES = ['320', '256', '192', '128']
    
    @classmethod
    def ensure_dirs(cls):
        """Ensure required directories exist."""
        cls.DOWNLOAD_DIR.mkdir(exist_ok=True)


# Create default instance
config = Config()
