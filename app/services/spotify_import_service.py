"""
Spotify Import Service — orchestrates Spotify playlist → YouTube Music matching → download.

Designed for reliability on Termux/Android:
- Sequential, one-track-at-a-time processing
- DB-persisted state (survives restarts)
- Retries with backoff on all network calls
- Per-track error isolation
"""

import logging
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from math import exp
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

SPOTIFY_PLAYLIST_RE = re.compile(
    r'https?://open\.spotify\.com/playlist/([a-zA-Z0-9]+)'
)

FORBIDDEN_WORDS = frozenset([
    'bassboosted', 'remix', 'remastered', 'remaster', 'reverb', 'bassboost',
    'live', 'acoustic', '8daudio', 'concert', 'acapella', 'slowed',
    'instrumental', 'cover', 'karaoke', 'nightcore', 'spedup',
])

NOISE_PATTERNS = re.compile(
    r'\s*[\(\[\{]'
    r'(?:official\s*(?:music\s*)?(?:video|audio|lyric(?:s)?|visuali[sz]er)|'
    r'lyrics?|audio|video|hd|hq|4k|remastered\s*\d*|'
    r'official\s*(?:hd\s*)?video)'
    r'[\)\]\}]\s*',
    re.IGNORECASE
)

FEAT_PATTERN = re.compile(
    r'\s*[\(\[]?\s*(?:feat\.?|ft\.?|featuring)\s+',
    re.IGNORECASE
)

# ─────────────────────────────────────────────
# Text normalization
# ─────────────────────────────────────────────

def slugify(text: str) -> str:
    """Normalize text for fuzzy comparison."""
    if not text:
        return ''
    text = str(text).lower()
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')  # strip accents
    text = re.sub(r'[^\w\s-]', '', text)       # strip punctuation
    text = re.sub(r'[-\s]+', '-', text).strip('-')
    return text


def strip_noise(title: str) -> str:
    """Remove (Official Video), [Audio], etc. from titles."""
    return NOISE_PATTERNS.sub('', title).strip()


def strip_feat(text: str) -> str:
    """Split at 'feat.' / 'ft.' and return the base part."""
    return FEAT_PATTERN.split(text)[0].strip()


# ─────────────────────────────────────────────
# Scoring functions
# ─────────────────────────────────────────────

def calc_name_match(spotify_title: str, yt_title: str) -> float:
    """Fuzzy title match after normalization."""
    s1 = slugify(strip_noise(strip_feat(spotify_title)))
    s2 = slugify(strip_noise(strip_feat(yt_title)))
    if not s1 or not s2:
        return 0.0
    return fuzz.ratio(s1, s2)


def calc_artist_match(spotify_artists: List[str], yt_artists: List[str]) -> float:
    """
    Match artists between Spotify and YouTube.
    Returns -1 if comparison is impossible.

    Handles Bollywood/Indian music where Spotify lists composer first
    (e.g. Pritam) while YouTube lists singer first (e.g. Arijit Singh).
    """
    if not spotify_artists or not yt_artists:
        return -1.0  # signal: unknown, don't penalize

    slug_sp = [slugify(a) for a in spotify_artists if a]
    slug_yt = [slugify(a) for a in yt_artists if a]

    if not slug_sp or not slug_yt:
        return -1.0

    # Find best match of ANY Spotify artist against YT primary artist
    # This handles composer-first ordering (Spotify: [Pritam, Arijit], YT: [Arijit])
    best_primary = max(fuzz.ratio(sp_a, slug_yt[0]) for sp_a in slug_sp)

    # Also check: does ANY Spotify artist appear anywhere in YT artist list?
    yt_combined = ' '.join(slug_yt)
    any_match = any(sp_a in yt_combined for sp_a in slug_sp)
    if any_match and best_primary < 80:
        best_primary = max(best_primary, 80)  # boost if substring match found

    # Fuzzy cross-match: best match of any SP artist vs any YT artist
    cross_best = max(
        fuzz.ratio(sp_a, yt_a)
        for sp_a in slug_sp
        for yt_a in slug_yt
    )
    best_primary = max(best_primary, cross_best)

    # If only one SP artist, done
    if len(slug_sp) <= 1:
        return best_primary

    # Secondary artist coverage: how many SP artists appear in YT
    matched_count = 0
    for sp_a in slug_sp:
        if sp_a in yt_combined:
            matched_count += 1
        elif max((fuzz.ratio(sp_a, ya) for ya in slug_yt), default=0) >= 70:
            matched_count += 1

    coverage = (matched_count / len(slug_sp)) * 100

    # Combine: primary match is more important than full coverage
    return max(best_primary, (best_primary + coverage) / 2)


def calc_time_match(spotify_duration_s: float, yt_duration_s: float) -> float:
    """Exponential decay duration scoring: exp(-0.1 * |diff|) * 100."""
    diff = abs(spotify_duration_s - yt_duration_s)
    return exp(-0.1 * diff) * 100


def check_forbidden_words(spotify_title: str, yt_title: str) -> Tuple[bool, List[str]]:
    """Check if YT title has forbidden words not in Spotify title."""
    sp_slug = slugify(spotify_title)
    yt_slug = slugify(yt_title)
    found = [w for w in FORBIDDEN_WORDS if w in yt_slug and w not in sp_slug]
    return len(found) > 0, found


def score_candidate(
    sp_title: str, sp_artists: List[str], sp_duration_s: float,
    yt_title: str, yt_artists: List[str], yt_duration_s: float,
    yt_album: Optional[str] = None, sp_album: Optional[str] = None,
    verified: bool = False
) -> Optional[float]:
    """
    Score a YouTube candidate against a Spotify track.
    Returns None if hard-rejected, otherwise a 0-100 score.

    Handles missing data gracefully:
    - If sp_artists is empty (scraper mode), skip artist matching.
    - If sp_duration_s is 0 (unknown), skip duration matching.
    """
    # Name match
    name_match = calc_name_match(sp_title, yt_title)

    # Forbidden words penalty
    has_forbidden, forbidden_list = check_forbidden_words(sp_title, yt_title)
    if has_forbidden:
        name_match -= 15 * len(forbidden_list)

    # Hard reject: name too different
    if name_match < 60:
        return None

    # Artist match (-1 means unknown/empty)
    artist_match = calc_artist_match(sp_artists, yt_artists)
    has_artist = artist_match >= 0

    # Hard reject: artist clearly wrong (only if we have artist data)
    if has_artist and artist_match < 70:
        return None

    # Time match (skip if duration unknown)
    has_duration = sp_duration_s > 0 and yt_duration_s > 0
    time_match = calc_time_match(sp_duration_s, yt_duration_s) if has_duration else -1.0

    # Hard reject: duration way off (>14s diff ≈ score <25)
    if has_duration and time_match < 25:
        return None

    # Combined score — adapt to available data
    if has_artist and has_duration:
        # Full data: name + artist + time
        average = (name_match + artist_match) / 2
        if average <= 85:
            average = (average + time_match) / 2
    elif has_artist:
        # No duration: name + artist only
        average = (name_match + artist_match) / 2
    elif has_duration:
        # No artist: name + time only
        average = (name_match + time_match) / 2
    else:
        # Title-only matching (scraper with no artist/duration)
        average = name_match

    # Album match boost for verified results
    if verified and yt_album and sp_album:
        album_match = fuzz.ratio(slugify(sp_album), slugify(yt_album))
        if album_match <= 80:
            average = (average + album_match) / 2

    # Low time + low average: skip (only if we have duration data)
    if has_duration and time_match < 50 and average < 75:
        return None

    return min(average, 100)


# ─────────────────────────────────────────────
# Spotify Client (embed page scraping — no API key needed)
# ─────────────────────────────────────────────

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
}

# Regex to extract __NEXT_DATA__ JSON from embed page
_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL
)


class SpotifyClient:
    """
    Fetches playlist tracks from Spotify's embed page.
    The embed endpoint returns server-rendered HTML with a __NEXT_DATA__ JSON
    blob containing complete track info (title, artists, duration, URI).
    No API key or authentication required.
    """

    def __init__(self):
        import requests as _requests
        self._session = _requests.Session()
        self._session.headers.update(_HEADERS)

    def fetch_playlist_tracks(self, playlist_url: str) -> Tuple[str, List[Dict]]:
        """
        Fetch tracks from a Spotify playlist via the embed page.

        Returns:
            (playlist_name, [track_dicts])
        """
        import json as _json

        match = SPOTIFY_PLAYLIST_RE.search(playlist_url)
        if not match:
            raise ValueError(f'Invalid Spotify playlist URL: {playlist_url}')

        playlist_id = match.group(1)
        embed_url = f'https://open.spotify.com/embed/playlist/{playlist_id}'

        # Fetch the embed page (contains __NEXT_DATA__ with full track info)
        resp = self._session.get(embed_url, timeout=20)
        resp.raise_for_status()
        html = resp.text

        # Extract __NEXT_DATA__ JSON
        nd_match = _NEXT_DATA_RE.search(html)
        if not nd_match:
            raise ValueError(
                'Could not parse playlist data from Spotify. '
                'The playlist may be private or the page format has changed.'
            )

        try:
            next_data = _json.loads(nd_match.group(1))
        except _json.JSONDecodeError as e:
            raise ValueError(f'Failed to parse Spotify data: {e}')

        # Navigate to entity data
        entity = (
            next_data
            .get('props', {})
            .get('pageProps', {})
            .get('state', {})
            .get('data', {})
            .get('entity', {})
        )

        if not entity:
            raise ValueError('Playlist data not found in Spotify response')

        playlist_name = entity.get('name') or entity.get('title') or 'Unknown Playlist'
        track_list = entity.get('trackList', [])

        if not track_list:
            raise ValueError(
                'No tracks found in this playlist. '
                'The playlist may be empty or private.'
            )

        # Parse track data
        tracks = []
        for item in track_list:
            title = item.get('title', '').strip()
            if not title:
                continue

            # subtitle contains artists separated by non-breaking spaces + commas
            # e.g. "Neha Kakkar,\u00a0Jubin Nautiyal,\u00a0Jaani"
            subtitle = item.get('subtitle', '')
            # Replace non-breaking spaces and clean up
            subtitle = subtitle.replace('\u00a0', ' ').strip()
            artists = [a.strip() for a in subtitle.split(',') if a.strip()]

            # Extract track ID from URI (spotify:track:XXXX)
            uri = item.get('uri', '')
            track_id = uri.split(':')[-1] if uri.startswith('spotify:track:') else ''

            tracks.append({
                'title': title,
                'artists': artists,
                'artist': ', '.join(artists),
                'album': '',  # embed data doesn't include album
                'duration_ms': item.get('duration', 0),
                'isrc': None,  # not available without API
                'explicit': item.get('isExplicit'),
                'track_id': track_id,
            })

        return playlist_name, tracks


# ─────────────────────────────────────────────
# YouTube Music Matcher
# ─────────────────────────────────────────────

class YouTubeMusicMatcher:
    """
    Searches YouTube Music via ytmusicapi and scores candidates.
    Initialized once and reused for an entire import job (RAM-friendly).
    """

    def __init__(self):
        from ytmusicapi import YTMusic
        self.ytm = YTMusic()

    def find_best_match(self, track: Dict) -> Optional[Dict]:
        """
        Search YouTube Music for the best match for a Spotify track.

        Returns:
            {video_id, url, title, artist, score, duration_s, verified}
            or None if no confident match found.
        """
        sp_title = track['title']
        sp_artists = track.get('artists', [])
        sp_artist = track.get('artist', '')
        sp_duration_s = track.get('duration_ms', 0) / 1000.0
        sp_album = track.get('album', '')
        sp_isrc = track.get('isrc')

        candidates = []

        # ── Step 1: ISRC search ──
        if sp_isrc:
            try:
                isrc_results = self.ytm.search(sp_isrc, filter='songs', limit=5,
                                               ignore_spelling=True)
                for r in isrc_results:
                    c = self._parse_result(r, is_song=True)
                    if c:
                        candidates.append(c)

                # If single verified ISRC hit, accept immediately
                if len(candidates) == 1 and candidates[0].get('verified'):
                    # Skip duration check if Spotify duration is unknown (scraper mode)
                    if sp_duration_s <= 0:
                        candidates[0]['score'] = 95.0
                        return candidates[0]
                    time_match = calc_time_match(sp_duration_s, candidates[0]['duration_s'])
                    if time_match >= 50:
                        candidates[0]['score'] = 95.0
                        return candidates[0]
            except Exception as e:
                logger.warning('ISRC search failed for %s: %s', sp_isrc, e)

        # ── Step 2: Title + Artist search (songs) ──
        query = f'{sp_title} {sp_artists[0]}' if sp_artists else sp_title
        try:
            song_results = self.ytm.search(query, filter='songs', limit=20,
                                           ignore_spelling=True)
            for r in song_results:
                c = self._parse_result(r, is_song=True)
                if c:
                    candidates.append(c)
        except Exception as e:
            logger.warning('Song search failed for "%s": %s', query, e)

        # Score all candidates so far
        best = self._pick_best(candidates, sp_title, sp_artists, sp_duration_s, sp_album)
        if best and best['score'] >= 75 and best.get('verified'):
            return best
        if best and best['score'] >= 80:
            return best

        # ── Step 3: Fallback to video search ──
        try:
            video_results = self.ytm.search(query, filter='videos', limit=20,
                                            ignore_spelling=True)
            for r in video_results:
                c = self._parse_result(r, is_song=False)
                if c:
                    candidates.append(c)
        except Exception as e:
            logger.warning('Video search failed for "%s": %s', query, e)

        # Final pick
        best = self._pick_best(candidates, sp_title, sp_artists, sp_duration_s, sp_album)
        if best and best['score'] >= 75 and best.get('verified'):
            return best
        if best and best['score'] >= 80:
            return best

        return None  # no confident match

    def _parse_result(self, result: Dict, is_song: bool) -> Optional[Dict]:
        """Parse a ytmusicapi search result into a normalized candidate dict."""
        if not result or not result.get('videoId'):
            return None

        artists = result.get('artists') or []
        artist_names = [a.get('name', '') for a in artists if isinstance(a, dict) and a.get('name')]

        duration_str = result.get('duration')
        duration_s = self._parse_duration(duration_str) if duration_str else 0

        album = None
        if isinstance(result.get('album'), dict):
            album = result['album'].get('name')

        video_id = result['videoId']
        result_type = result.get('resultType', '')

        return {
            'video_id': video_id,
            'url': f'https://music.youtube.com/watch?v={video_id}' if is_song
                   else f'https://www.youtube.com/watch?v={video_id}',
            'title': result.get('title', ''),
            'artists': artist_names,
            'artist': ', '.join(artist_names),
            'album': album,
            'duration_s': duration_s,
            'verified': result_type == 'song',
            'score': 0.0,
        }

    def _pick_best(
        self, candidates: List[Dict],
        sp_title: str, sp_artists: List[str], sp_duration_s: float, sp_album: str
    ) -> Optional[Dict]:
        """Score all candidates and return the best one."""
        best = None
        best_score = 0.0

        seen_ids = set()
        for c in candidates:
            vid = c['video_id']
            if vid in seen_ids:
                continue
            seen_ids.add(vid)

            score = score_candidate(
                sp_title=sp_title,
                sp_artists=sp_artists,
                sp_duration_s=sp_duration_s,
                yt_title=c['title'],
                yt_artists=c['artists'],
                yt_duration_s=c['duration_s'],
                yt_album=c.get('album'),
                sp_album=sp_album,
                verified=c.get('verified', False),
            )
            if score is not None and score > best_score:
                best_score = score
                c['score'] = round(score, 1)
                best = c

        return best

    @staticmethod
    def _parse_duration(duration_str: str) -> float:
        """Parse '3:45' or '1:02:30' into seconds."""
        if not duration_str:
            return 0
        parts = str(duration_str).split(':')
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            else:
                return float(parts[0])
        except (ValueError, IndexError):
            return 0


# ─────────────────────────────────────────────
# Import Service (orchestrator)
# ─────────────────────────────────────────────

class SpotifyImportService:
    """
    Main orchestrator: submit jobs, process in background, query status.
    """

    _lock = threading.Lock()
    _active_jobs = set()  # job IDs currently being processed

    def start_job(self, playlist_url: str, user_id: int, app) -> Dict:
        """
        Create and start a Spotify import job.

        Args:
            playlist_url: Spotify playlist URL
            user_id: Current user ID
            app: Flask app instance (for background thread context)

        Returns:
            Job dict with id, status, playlist_url
        """
        from app.models import SpotifyImportJob
        from app.models.database import db

        # Validate URL
        if not SPOTIFY_PLAYLIST_RE.search(playlist_url):
            raise ValueError('Invalid Spotify playlist URL')

        # Guard: don't allow the same playlist to be imported concurrently
        existing = SpotifyImportJob.query.filter_by(
            playlist_url=playlist_url,
            status='processing',
        ).first()
        if existing:
            raise ValueError('This playlist is already being imported')

        # Create a placeholder job immediately (don't block on scraping)
        job = SpotifyImportJob(
            user_id=user_id,
            playlist_url=playlist_url,
            playlist_name='Loading...',
            status='pending',
            total_tracks=0,
        )
        db.session.add(job)
        db.session.commit()

        job_id = job.id
        job_dict = job.to_dict()

        # Start background thread (scraping + matching happens there)
        t = threading.Thread(
            target=self._process_job,
            args=(app, job_id, playlist_url),
            daemon=True,
            name=f'spotify-import-{job_id[:8]}',
        )
        t.start()

        return job_dict

    def _process_job(self, app, job_id: str, playlist_url: str):
        """Background worker: scrape playlist, then iterate tracks, match, download."""
        with app.app_context():
            from app.models import SpotifyImportJob, SpotifyImportTrack, Download
            from app.models.database import db
            from app.services.queue_service import queue_service

            job = SpotifyImportJob.query.get(job_id)
            if not job:
                return

            with self._lock:
                self._active_jobs.add(job_id)

            try:
                # ── Phase 1: Scrape playlist ──
                job.status = 'processing'
                job.current_track = 'Fetching playlist from Spotify...'
                db.session.commit()

                spotify = SpotifyClient()
                playlist_name, tracks_data = spotify.fetch_playlist_tracks(playlist_url)

                if not tracks_data:
                    job.status = 'failed'
                    job.error_message = 'Playlist is empty or contains no playable tracks'
                    db.session.commit()
                    return

                # Update job with real data
                job.playlist_name = playlist_name
                job.total_tracks = len(tracks_data)

                # Create track records
                for t in tracks_data:
                    track = SpotifyImportTrack(
                        job_id=job.id,
                        title=t['title'],
                        artist=t.get('artist', ''),
                        album=t.get('album', ''),
                        isrc=t.get('isrc'),
                        duration_ms=t.get('duration_ms', 0),
                        explicit=t.get('explicit'),
                        status='pending',
                    )
                    db.session.add(track)

                db.session.commit()

                # ── Phase 2: Match and download ──
                matcher = YouTubeMusicMatcher()
                tracks = SpotifyImportTrack.query.filter_by(job_id=job_id).all()

                for i, track in enumerate(tracks):
                    if track.status in ('downloaded', 'skipped', 'failed'):
                        continue  # already processed (resume support)

                    try:
                        self._process_single_track(
                            db, job, track, matcher, queue_service
                        )
                    except Exception as e:
                        logger.exception('Error processing track %s: %s', track.title, e)
                        track.status = 'failed'
                        track.reason = f'Error: {str(e)[:200]}'
                        job.failed += 1

                    # Update current track display
                    remaining = job.total_tracks - (job.downloaded + job.skipped + job.failed)
                    if remaining > 0:
                        next_idx = min(i + 1, len(tracks) - 1)
                        job.current_track = f'{tracks[next_idx].artist} - {tracks[next_idx].title}'
                    else:
                        job.current_track = ''

                    db.session.commit()

                    # Rate-limit: 1s between searches (Termux-friendly)
                    time.sleep(1)

                # Done
                job.status = 'completed'
                job.completed_at = datetime.now(timezone.utc)
                job.current_track = ''
                db.session.commit()

            except Exception as e:
                logger.exception('Job %s failed: %s', job_id, e)
                job.status = 'failed'
                job.error_message = str(e)[:500]
                db.session.commit()

            finally:
                with self._lock:
                    self._active_jobs.discard(job_id)

    def _process_single_track(self, db, job, track, matcher, queue_service):
        """Match and download a single track."""
        from app.models import Download

        track.status = 'matching'
        job.current_track = f'{track.artist} - {track.title}'
        db.session.commit()

        # Build track dict for matcher
        track_info = {
            'title': track.title,
            'artists': [a.strip() for a in track.artist.split(',') if a.strip()],
            'artist': track.artist,
            'album': track.album,
            'duration_ms': track.duration_ms,
            'isrc': track.isrc,
        }

        # Search YouTube Music
        match = matcher.find_best_match(track_info)

        if not match:
            track.status = 'skipped'
            track.reason = 'No confident match found'
            job.skipped += 1
            return

        track.video_id = match['video_id']
        track.score = match['score']

        # Check duplicate in existing library
        is_dup, existing_file = Download.check_duplicate(
            title=match.get('title', track.title),
            video_id=match['video_id'],
            artist=match.get('artist', track.artist),
            duration=match.get('duration_s', 0),
        )
        if is_dup:
            track.status = 'downloaded'
            track.reason = 'Already in library'
            job.downloaded += 1
            return

        # Queue the download
        track.status = 'downloading'
        db.session.commit()

        try:
            result = queue_service.add(
                url=match['url'],
                title=match.get('title', track.title),
                thumbnail=f"https://i.ytimg.com/vi/{match['video_id']}/mqdefault.jpg",
                video_id=match['video_id'],
                artist=match.get('artist', track.artist),
                duration=match.get('duration_s', 0),
            )

            # Wait for download to complete (poll with timeout)
            queue_item = result.get('queue_item', {})
            job_item_id = queue_item.get('id') if isinstance(queue_item, dict) else None
            if job_item_id:
                dl_ok = self._wait_for_download(queue_service, job_item_id, timeout=120)
            else:
                dl_ok = True  # no queue item to track, assume success

            if dl_ok:
                track.status = 'downloaded'
                job.downloaded += 1
            else:
                track.status = 'failed'
                track.reason = 'Download timed out'
                job.failed += 1

        except Exception as e:
            logger.warning('Download failed for %s: %s', match['video_id'], e)
            track.status = 'failed'
            track.reason = f'Download error: {str(e)[:200]}'
            job.failed += 1

    def _wait_for_download(self, queue_service, job_id: str, timeout: int = 120) -> bool:
        """Poll queue service until download completes or times out.
        Returns True if download completed successfully, False on timeout or error."""
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(2)
            all_downloads = queue_service.get_all()
            active_list = all_downloads.get('active', [])
            # Find our job in active downloads
            job_entry = next(
                (item for item in active_list
                 if isinstance(item, dict) and item.get('id') == job_id),
                None
            )
            if job_entry is None:
                # Not in active list anymore — check queue too
                queue_list = all_downloads.get('queue', [])
                in_queue = any(
                    isinstance(item, dict) and item.get('id') == job_id
                    for item in queue_list
                )
                if not in_queue:
                    return True  # finished and cleaned up = success
            elif job_entry.get('status') == 'completed':
                return True
            elif job_entry.get('status') in ('error', 'skipped'):
                return False
        # Timeout
        logger.warning('Download wait timed out for queue item %s', job_id)
        return False

    @staticmethod
    def get_job_status(job_id: str) -> Optional[Dict]:
        """Get job status with tracks."""
        from app.models import SpotifyImportJob
        job = SpotifyImportJob.query.get(job_id)
        if not job:
            return None
        return job.to_dict(include_tracks=True)

    @staticmethod
    def get_user_jobs(user_id: int, limit: int = 10) -> List[Dict]:
        """Get recent jobs for a user."""
        from app.models import SpotifyImportJob
        jobs = (
            SpotifyImportJob.query
            .filter_by(user_id=user_id)
            .order_by(SpotifyImportJob.created_at.desc())
            .limit(limit)
            .all()
        )
        return [j.to_dict() for j in jobs]


# Global singleton
spotify_import_service = SpotifyImportService()
