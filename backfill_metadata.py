#!/usr/bin/env python3
"""
Backfill Metadata — One-time script to enrich existing downloads.

Fetches language, genre, tags, and album info from YouTube for all
downloads that have a valid video_id but are missing metadata.

Usage:
    python backfill_metadata.py              # Process all un-enriched songs
    python backfill_metadata.py --force      # Re-process ALL songs (overwrite)
    python backfill_metadata.py --dry-run    # Preview without writing to DB
    python backfill_metadata.py --limit 10   # Process only first N songs

Runs on Termux/production — uses delays between requests to avoid throttling.
"""

import json
import os
import sys
import time
import argparse

# ── Load .env (same logic as manage.py) ──────────────────────────────────────
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

_load_dotenv()

# ── Language detection from tags/title ───────────────────────────────────────
LANGUAGE_KEYWORDS = {
    'tamil':      ['tamil', 'kollywood', 'தமிழ்'],
    'hindi':      ['hindi', 'bollywood', 'हिन्दी', 'हिंदी'],
    'english':    ['english', 'pop music', 'billboard', 'western'],
    'malayalam':  ['malayalam', 'mollywood', 'മലയാളം'],
    'telugu':     ['telugu', 'tollywood', 'తెలుగు'],
    'kannada':    ['kannada', 'sandalwood', 'ಕನ್ನಡ'],
    'bengali':    ['bengali', 'bangla', 'বাংলা'],
    'punjabi':    ['punjabi', 'ਪੰਜਾਬੀ'],
    'marathi':    ['marathi', 'मराठी'],
    'gujarati':   ['gujarati', 'ગુજરાતી'],
    'korean':     ['korean', 'k-pop', 'kpop', '한국어'],
    'japanese':   ['japanese', 'j-pop', 'jpop', '日本語'],
    'spanish':    ['spanish', 'latino', 'reggaeton', 'español'],
    'arabic':     ['arabic', 'عربي'],
    'french':     ['french', 'français'],
}

# ── Genre detection from tags/title ──────────────────────────────────────────
GENRE_KEYWORDS = {
    'pop':        ['pop', 'pop music', 'pop song'],
    'rock':       ['rock', 'rock music', 'alternative rock', 'indie rock'],
    'hip-hop':    ['hip hop', 'hip-hop', 'rap', 'trap', 'hiphop'],
    'r&b':        ['r&b', 'rnb', 'soul', 'rhythm and blues'],
    'electronic': ['electronic', 'edm', 'house', 'techno', 'trance', 'dubstep'],
    'lo-fi':      ['lofi', 'lo-fi', 'chillhop', 'study beats', 'lo fi'],
    'classical':  ['classical', 'carnatic', 'hindustani', 'raag', 'orchestra'],
    'jazz':       ['jazz', 'smooth jazz', 'bebop'],
    'romantic':   ['romantic', 'love song', 'romance', 'melody', 'love'],
    'devotional': ['devotional', 'bhajan', 'bhakti', 'worship', 'gospel'],
    'folk':       ['folk', 'folk music', 'acoustic folk'],
    'indie':      ['indie', 'indie music', 'indie pop', 'indie folk'],
    'metal':      ['metal', 'heavy metal', 'death metal', 'metalcore'],
    'country':    ['country', 'country music', 'nashville'],
    'reggae':     ['reggae', 'dancehall', 'ska'],
    'chill':      ['chill', 'ambient', 'relaxing', 'calm', 'peaceful'],
    'workout':    ['workout', 'gym', 'fitness', 'motivation', 'pump up'],
    'party':      ['party', 'dance', 'club', 'dj mix'],
    'sad':        ['sad', 'emotional', 'heartbreak', 'pain', 'crying'],
    'film':       ['soundtrack', 'ost', 'film music', 'movie song', 'film song'],
}


def detect_language(tags, title, description=''):
    """Detect language from tags, title, and description."""
    searchable = ' '.join([
        ' '.join(tags).lower(),
        (title or '').lower(),
        (description or '').lower()[:500],
    ])

    scores = {}
    for lang, keywords in LANGUAGE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in searchable)
        if count > 0:
            scores[lang] = count

    if scores:
        return max(scores, key=scores.get)
    return None


def detect_genre(tags, title, description=''):
    """Detect genre from tags, title, and description."""
    searchable = ' '.join([
        ' '.join(tags).lower(),
        (title or '').lower(),
        (description or '').lower()[:500],
    ])

    scores = {}
    for genre, keywords in GENRE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in searchable)
        if count > 0:
            scores[genre] = count

    if scores:
        return max(scores, key=scores.get)
    return None


def fetch_metadata(video_id):
    """Fetch metadata from YouTube for a given video ID."""
    import yt_dlp

    url = f'https://www.youtube.com/watch?v={video_id}'
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'socket_timeout': 15,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            tags = info.get('tags') or []
            title = info.get('title') or ''
            description = info.get('description') or ''
            categories = info.get('categories') or []

            # Combine tags + categories for detection
            all_tags = [str(t).lower().strip() for t in tags + categories if t]

            return {
                'tags': all_tags,
                'title': title,
                'description': description,
                'album': info.get('album') or '',
                'artist': info.get('artist') or info.get('uploader') or '',
                'genre_raw': info.get('genre') or '',
                'language_raw': info.get('language') or '',
            }
    except Exception as e:
        return {'error': str(e)}


def main():
    parser = argparse.ArgumentParser(description='Backfill song metadata from YouTube')
    parser.add_argument('--force', action='store_true',
                        help='Re-process all songs, even those already enriched')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without writing to DB')
    parser.add_argument('--limit', type=int, default=0,
                        help='Max songs to process (0 = all)')
    parser.add_argument('--delay', type=float, default=2.0,
                        help='Delay in seconds between YouTube requests (default: 2)')
    args = parser.parse_args()

    # ── Boot Flask app ───────────────────────────────────────────────────────
    from app import create_app
    app = create_app()

    with app.app_context():
        from app.models import db, Download

        # Add new columns if they don't exist (safe for SQLite)
        with db.engine.connect() as conn:
            existing = [row[1] for row in conn.execute(db.text("PRAGMA table_info('downloads')"))]
            for col, col_type in [
                ('language', 'VARCHAR(50)'),
                ('genre', 'VARCHAR(100)'),
                ('tags', 'TEXT'),
                ('album', 'VARCHAR(300)'),
            ]:
                if col not in existing:
                    conn.execute(db.text(f"ALTER TABLE downloads ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    print(f"  ✅ Added column '{col}' to downloads table")

        # ── Query songs to process ───────────────────────────────────────────
        query = Download.query.filter(
            Download.video_id.isnot(None),
            ~Download.video_id.like('local_%'),
        )

        if not args.force:
            # Only process songs without metadata
            query = query.filter(
                (Download.tags.is_(None)) | (Download.tags == '')
            )

        query = query.order_by(Download.downloaded_at.desc())

        if args.limit > 0:
            query = query.limit(args.limit)

        songs = query.all()

        if not songs:
            print('✅ No songs to process. All downloads already have metadata.')
            print('   Use --force to re-process everything.')
            return

        print(f'\n🎵 Found {len(songs)} song(s) to enrich')
        if args.dry_run:
            print('   (DRY RUN — no changes will be saved)\n')
        print()

        # ── Process each song ────────────────────────────────────────────────
        success = 0
        skipped = 0
        failed = 0

        for i, song in enumerate(songs, 1):
            label = f'[{i}/{len(songs)}]'
            print(f'{label} {song.title}')
            print(f'       video_id: {song.video_id}')

            meta = fetch_metadata(song.video_id)

            if meta is None:
                print(f'       ⚠️  No data returned (video may be deleted)')
                failed += 1
                print()
                time.sleep(args.delay)
                continue

            if 'error' in meta:
                print(f'       ❌ Error: {meta["error"][:100]}')
                failed += 1
                print()
                time.sleep(args.delay)
                continue

            # Detect language
            lang = meta.get('language_raw') or detect_language(
                meta['tags'], meta['title'], meta['description']
            )

            # Detect genre
            genre = meta.get('genre_raw') or detect_genre(
                meta['tags'], meta['title'], meta['description']
            )

            # Normalize to canonical forms (hi → hindi, etc.)
            from normalize_metadata import normalize_language, normalize_genre, normalize_artist
            lang = normalize_language(lang) if lang else lang
            genre = normalize_genre(genre) if genre else genre

            tags_json = json.dumps(meta['tags'][:30]) if meta['tags'] else '[]'
            album = meta.get('album', '') or ''

            # Also update artist if we got a better one from yt-dlp
            better_artist = meta.get('artist', '')

            print(f'       language: {lang or "—"}')
            print(f'       genre:    {genre or "—"}')
            print(f'       album:    {album or "—"}')
            print(f'       tags:     {meta["tags"][:5]}{"..." if len(meta["tags"]) > 5 else ""}')

            if not args.dry_run:
                song.language = lang
                song.genre = genre
                song.tags = tags_json
                song.album = album
                # Update artist only if current is missing/unknown
                if better_artist and (
                    not song.artist
                    or song.artist.lower() in ('unknown', 'unknown artist', '')
                ):
                    song.artist = better_artist
                    print(f'       artist:   {better_artist} (updated)')

                db.session.commit()
                print(f'       ✅ Saved')
            else:
                print(f'       (dry run — not saved)')

            success += 1
            print()

            # Rate limiting
            if i < len(songs):
                time.sleep(args.delay)

        # ── Summary ──────────────────────────────────────────────────────────
        print('─' * 50)
        print(f'✅ Done!  success={success}  skipped={skipped}  failed={failed}')
        if args.dry_run:
            print('   (DRY RUN — no changes were saved)')
        print()


if __name__ == '__main__':
    main()
