"""
Services package for YT Music Downloader.
"""

from .youtube import YouTubeService
from .queue_service import QueueService
from .normalization import normalize_language, normalize_genre, normalize_artist
from .recommendation import RecommendationEngine, recommendation_engine

__all__ = [
    'YouTubeService',
    'QueueService',
    'normalize_language',
    'normalize_genre',
    'normalize_artist',
    'RecommendationEngine',
    'recommendation_engine',
]
