"""
Dynamic storage path resolution for downloads and thumbnails.
"""

import os
from pathlib import Path

from config import config


def _normalize_dir(raw_value: str) -> Path:
    """Expand and normalize a configured directory path."""
    value = str(raw_value or '').strip()
    if not value:
        return config.DOWNLOAD_DIR

    expanded = os.path.expanduser(os.path.expandvars(value))
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = (config.BASE_DIR / candidate).resolve()
    return candidate


def get_download_dir() -> Path:
    """
    Resolve current download directory dynamically.

    Priority:
    1) `ZORA_DOWNLOAD_DIR` environment variable.
    2) DB setting `download_dir`.
    3) Config default path.
    """
    env_override = os.getenv('ZORA_DOWNLOAD_DIR', '').strip()
    if env_override:
        path = _normalize_dir(env_override)
        path.mkdir(parents=True, exist_ok=True)
        return path

    db_value = ''
    try:
        from app.models import Settings

        db_value = str(Settings.get('download_dir', '') or '').strip()
    except Exception:
        db_value = ''

    path = _normalize_dir(db_value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_thumbnails_dir() -> Path:
    """Resolve thumbnails directory alongside current download directory."""
    path = get_download_dir() / 'thumbnails'
    path.mkdir(parents=True, exist_ok=True)
    return path

