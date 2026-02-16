"""
Dynamic download preference helpers.
"""

from typing import Tuple


SUPPORTED_AUDIO_FORMATS = ('m4a', 'mp3', 'aac', 'ogg', 'opus', 'flac', 'wav', 'webm', 'mka')
DEFAULT_AUDIO_FORMAT = 'm4a'
DEFAULT_AUDIO_QUALITY = '320'
MIN_AUDIO_QUALITY = 64
MAX_AUDIO_QUALITY = 512


def _clamp_quality(raw_value) -> str:
    """Normalize quality to a bounded integer kbps string."""
    try:
        parsed = int(str(raw_value).strip())
        parsed = max(MIN_AUDIO_QUALITY, min(parsed, MAX_AUDIO_QUALITY))
        return str(parsed)
    except Exception:
        return DEFAULT_AUDIO_QUALITY


def get_default_download_preferences() -> Tuple[str, str]:
    """Resolve default format/quality from settings with safe fallbacks."""
    audio_format = DEFAULT_AUDIO_FORMAT
    quality = DEFAULT_AUDIO_QUALITY

    try:
        from app.models import Settings

        configured_format = str(
            Settings.get('default_format', DEFAULT_AUDIO_FORMAT) or ''
        ).lower().lstrip('.')
        if configured_format in SUPPORTED_AUDIO_FORMATS:
            audio_format = configured_format

        quality = _clamp_quality(
            Settings.get('default_quality', DEFAULT_AUDIO_QUALITY)
        )
    except Exception:
        pass

    return audio_format, quality


def get_preferred_audio_exts():
    """Return preferred extension order with configured format first."""
    preferred_format, _ = get_default_download_preferences()
    ordered = list(SUPPORTED_AUDIO_FORMATS)
    if preferred_format in ordered:
        ordered.remove(preferred_format)
        ordered.insert(0, preferred_format)
    return [f'.{fmt}' for fmt in ordered]


def get_default_quality_label() -> str:
    """Return normalized quality label (e.g. 320kbps)."""
    _, quality = get_default_download_preferences()
    return f'{quality}kbps'

