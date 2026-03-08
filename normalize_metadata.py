#!/usr/bin/env python3
"""
Normalize Metadata — Clean up inconsistent language, genre, and artist data.

Runs PURELY on existing DB data. No yt-dlp API calls.
Maps all variations (ISO codes, typos, abbreviations, native scripts)
to a single canonical form.

Usage:
    python normalize_metadata.py              # Normalize all songs
    python normalize_metadata.py --dry-run    # Preview without writing
    python normalize_metadata.py --stats      # Show current data distribution
"""

import json
import os
import re
import argparse


# ── Load .env ────────────────────────────────────────────────────────────────
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


# ═══════════════════════════════════════════════════════════════════════════════
#  LANGUAGE ALIAS MAP
#  Maps every known variation → one canonical lowercase name.
#  Covers: ISO 639-1 codes, ISO 639-2 codes, native script names,
#  common misspellings, YouTube/yt-dlp raw values.
# ═══════════════════════════════════════════════════════════════════════════════
LANGUAGE_ALIASES = {
    # ── Hindi ────────────────────────────────────────────────────────────────
    'hindi': [
        'hi', 'hin', 'hind', 'hindhi', 'hidi', 'hinid',
        'bollywood', 'हिन्दी', 'हिंदी', 'hindi song', 'hindi songs',
        'hindi music', 'hindi pop', 'hindi rap', 'indian',
    ],
    # ── Tamil ────────────────────────────────────────────────────────────────
    'tamil': [
        'ta', 'tam', 'tamizh', 'thamizh', 'தமிழ்', 'தமிழ',
        'kollywood', 'tamil song', 'tamil songs', 'tamil music',
    ],
    # ── Telugu ───────────────────────────────────────────────────────────────
    'telugu': [
        'te', 'tel', 'తెలుగు', 'tollywood', 'telugu song', 'telugu songs',
        'telugu music',
    ],
    # ── Malayalam ─────────────────────────────────────────────────────────────
    'malayalam': [
        'ml', 'mal', 'mlm', 'മലയാളം', 'mollywood',
        'malayalam song', 'malayalam songs', 'malayalam music',
    ],
    # ── Kannada ──────────────────────────────────────────────────────────────
    'kannada': [
        'kn', 'kan', 'ಕನ್ನಡ', 'sandalwood',
        'kannada song', 'kannada songs', 'kannada music',
    ],
    # ── Bengali ──────────────────────────────────────────────────────────────
    'bengali': [
        'bn', 'ben', 'bangla', 'বাংলা', 'bangali',
        'bengali song', 'bengali songs', 'bengali music',
    ],
    # ── Punjabi ──────────────────────────────────────────────────────────────
    'punjabi': [
        'pa', 'pan', 'panjabi', 'ਪੰਜਾਬੀ', 'پنجابی',
        'punjabi song', 'punjabi songs', 'punjabi music',
    ],
    # ── Marathi ──────────────────────────────────────────────────────────────
    'marathi': [
        'mr', 'mar', 'मराठी', 'marathi song', 'marathi songs',
    ],
    # ── Gujarati ─────────────────────────────────────────────────────────────
    'gujarati': [
        'gu', 'guj', 'ગુજરાતી', 'gujarati song', 'gujarati songs',
    ],
    # ── Urdu ─────────────────────────────────────────────────────────────────
    'urdu': [
        'ur', 'urd', 'اردو', 'urdu song', 'urdu songs',
    ],
    # ── English ──────────────────────────────────────────────────────────────
    'english': [
        'en', 'eng', 'en-us', 'en-gb', 'en-au', 'en-in',
        'english song', 'english songs', 'english music',
        'pop music', 'billboard', 'western',
    ],
    # ── Korean ───────────────────────────────────────────────────────────────
    'korean': [
        'ko', 'kor', 'k-pop', 'kpop', '한국어', '한국',
        'korean song', 'korean songs', 'korean music',
    ],
    # ── Japanese ─────────────────────────────────────────────────────────────
    'japanese': [
        'ja', 'jpn', 'j-pop', 'jpop', '日本語', '日本',
        'japanese song', 'japanese songs', 'japanese music', 'anime',
    ],
    # ── Spanish ──────────────────────────────────────────────────────────────
    'spanish': [
        'es', 'spa', 'español', 'espanol', 'castellano',
        'latino', 'reggaeton', 'latin',
        'spanish song', 'spanish songs', 'spanish music',
    ],
    # ── Arabic ───────────────────────────────────────────────────────────────
    'arabic': [
        'ar', 'ara', 'عربي', 'العربية',
        'arabic song', 'arabic songs', 'arabic music',
    ],
    # ── French ───────────────────────────────────────────────────────────────
    'french': [
        'fr', 'fra', 'fre', 'français', 'francais',
        'french song', 'french songs', 'french music',
    ],
    # ── Portuguese ───────────────────────────────────────────────────────────
    'portuguese': [
        'pt', 'por', 'pt-br', 'português', 'portugues',
        'brazilian', 'portuguese song',
    ],
    # ── Russian ──────────────────────────────────────────────────────────────
    'russian': [
        'ru', 'rus', 'русский', 'russian song', 'russian songs',
    ],
    # ── German ───────────────────────────────────────────────────────────────
    'german': [
        'de', 'deu', 'ger', 'deutsch', 'german song', 'german songs',
    ],
    # ── Chinese ──────────────────────────────────────────────────────────────
    'chinese': [
        'zh', 'zho', 'chi', 'zh-hans', 'zh-hant', 'zh-cn', 'zh-tw',
        '中文', '中国', 'mandarin', 'cantonese', 'cpop', 'c-pop',
        'chinese song', 'chinese songs',
    ],
    # ── Turkish ──────────────────────────────────────────────────────────────
    'turkish': [
        'tr', 'tur', 'türkçe', 'turkce', 'turkish song',
    ],
    # ── Italian ──────────────────────────────────────────────────────────────
    'italian': [
        'it', 'ita', 'italiano', 'italian song',
    ],
    # ── Thai ─────────────────────────────────────────────────────────────────
    'thai': [
        'th', 'tha', 'ภาษาไทย', 'thai song',
    ],
    # ── Vietnamese ───────────────────────────────────────────────────────────
    'vietnamese': [
        'vi', 'vie', 'tiếng việt', 'vietnamese song',
    ],
    # ── Indonesian ───────────────────────────────────────────────────────────
    'indonesian': [
        'id', 'ind', 'bahasa indonesia', 'indonesian song',
    ],
    # ── Malay ────────────────────────────────────────────────────────────────
    'malay': [
        'ms', 'msa', 'may', 'bahasa melayu', 'malay song',
    ],
    # ── Nepali ───────────────────────────────────────────────────────────────
    'nepali': [
        'ne', 'nep', 'नेपाली', 'nepali song',
    ],
    # ── Sinhala ──────────────────────────────────────────────────────────────
    'sinhala': [
        'si', 'sin', 'sinhalese', 'සිංහල', 'sinhala song',
    ],
    # ── Assamese ─────────────────────────────────────────────────────────────
    'assamese': [
        'as', 'asm', 'অসমীয়া', 'assamese song',
    ],
    # ── Odia ─────────────────────────────────────────────────────────────────
    'odia': [
        'or', 'ori', 'oriya', 'ଓଡ଼ିଆ', 'odia song',
    ],
    # ── Bhojpuri ─────────────────────────────────────────────────────────────
    'bhojpuri': [
        'bho', 'bhojpuri song', 'bhojpuri songs', 'bhojpuri music',
    ],
    # ── Haryanvi ─────────────────────────────────────────────────────────────
    'haryanvi': [
        'haryanvi song', 'haryanvi songs', 'haryanvi music',
    ],
    # ── Rajasthani ───────────────────────────────────────────────────────────
    'rajasthani': [
        'rajasthani song', 'rajasthani songs', 'rajasthani music',
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
#  GENRE ALIAS MAP
#  Maps every known variation → one canonical lowercase name.
# ═══════════════════════════════════════════════════════════════════════════════
GENRE_ALIASES = {
    # ── Pop ──────────────────────────────────────────────────────────────────
    'pop': [
        'pop music', 'pop song', 'pop songs', 'pop rock',
        'synthpop', 'synth-pop', 'electropop', 'dance pop', 'dance-pop',
        'teen pop', 'bubblegum pop', 'art pop',
    ],
    # ── Rock ─────────────────────────────────────────────────────────────────
    'rock': [
        'rock music', 'rock song', 'alternative rock', 'alt rock',
        'alt-rock', 'indie rock', 'classic rock', 'soft rock',
        'hard rock', 'punk rock', 'punk', 'post-punk', 'grunge',
        'progressive rock', 'prog rock', 'psychedelic rock',
        'garage rock', 'blues rock',
    ],
    # ── Hip-Hop ──────────────────────────────────────────────────────────────
    'hip-hop': [
        'hip hop', 'hiphop', 'hip-hop music', 'rap', 'rap music',
        'trap', 'trap music', 'mumble rap', 'gangsta rap',
        'conscious rap', 'boom bap', 'old school hip hop',
        'underground hip hop', 'desi hip hop', 'indian hip hop',
        'gully rap',
    ],
    # ── R&B ──────────────────────────────────────────────────────────────────
    'r&b': [
        'rnb', 'r and b', 'r & b', 'rhythm and blues',
        'soul', 'soul music', 'neo-soul', 'neo soul',
        'contemporary r&b', 'urban contemporary',
    ],
    # ── Electronic ───────────────────────────────────────────────────────────
    'electronic': [
        'edm', 'electronic music', 'electronic dance music',
        'house', 'house music', 'deep house', 'tech house',
        'techno', 'trance', 'dubstep', 'drum and bass', 'dnb',
        'd&b', 'drum & bass', 'hardstyle', 'psytrance',
        'progressive house', 'electro house', 'future bass',
        'synthwave', 'retrowave', 'electronica',
    ],
    # ── Lo-fi ────────────────────────────────────────────────────────────────
    'lo-fi': [
        'lofi', 'lo fi', 'lo-fi hip hop', 'lofi hip hop',
        'chillhop', 'study beats', 'lofi beats',
        'lo-fi beats', 'lofi music', 'lo-fi music',
        'chill beats', 'study music',
    ],
    # ── Classical ────────────────────────────────────────────────────────────
    'classical': [
        'classical music', 'carnatic', 'carnatic music',
        'hindustani', 'hindustani classical', 'raag', 'raga',
        'orchestra', 'orchestral', 'symphony', 'chamber music',
        'semi-classical', 'semi classical', 'indian classical',
    ],
    # ── Jazz ─────────────────────────────────────────────────────────────────
    'jazz': [
        'jazz music', 'smooth jazz', 'bebop', 'swing',
        'jazz fusion', 'acid jazz', 'cool jazz', 'free jazz',
        'nu jazz', 'vocal jazz',
    ],
    # ── Romantic ─────────────────────────────────────────────────────────────
    'romantic': [
        'romance', 'love song', 'love songs', 'love',
        'love music', 'romantic song', 'romantic songs',
        'romantic music', 'melody', 'melodious',
    ],
    # ── Devotional ───────────────────────────────────────────────────────────
    'devotional': [
        'bhajan', 'bhakti', 'devotional song', 'devotional songs',
        'worship', 'gospel', 'gospel music', 'spiritual',
        'kirtan', 'mantra', 'aarti', 'arti', 'qawwali',
        'sufi', 'sufi music', 'religious',
    ],
    # ── Folk ─────────────────────────────────────────────────────────────────
    'folk': [
        'folk music', 'folk song', 'folk songs', 'acoustic folk',
        'folk rock', 'indian folk', 'desi folk',
    ],
    # ── Indie ────────────────────────────────────────────────────────────────
    'indie': [
        'indie music', 'indie pop', 'indie folk', 'indie electronic',
        'independent', 'independent music',
    ],
    # ── Metal ────────────────────────────────────────────────────────────────
    'metal': [
        'heavy metal', 'death metal', 'metalcore', 'black metal',
        'thrash metal', 'power metal', 'doom metal', 'nu metal',
        'nu-metal', 'progressive metal', 'symphonic metal',
        'deathcore', 'metal music',
    ],
    # ── Country ──────────────────────────────────────────────────────────────
    'country': [
        'country music', 'country song', 'country songs',
        'nashville', 'country rock', 'country pop',
        'americana', 'bluegrass',
    ],
    # ── Reggae ───────────────────────────────────────────────────────────────
    'reggae': [
        'reggae music', 'dancehall', 'ska', 'dub', 'roots reggae',
        'reggaeton',
    ],
    # ── Chill ────────────────────────────────────────────────────────────────
    'chill': [
        'ambient', 'ambient music', 'relaxing', 'relaxing music',
        'calm', 'calm music', 'peaceful', 'meditation', 'zen',
        'sleep music', 'nature sounds', 'asmr',
    ],
    # ── Workout ──────────────────────────────────────────────────────────────
    'workout': [
        'gym', 'gym music', 'fitness', 'fitness music',
        'motivation', 'motivational', 'pump up', 'power music',
        'workout music', 'exercise',
    ],
    # ── Party ────────────────────────────────────────────────────────────────
    'party': [
        'dance', 'dance music', 'club', 'club music',
        'dj mix', 'dj', 'party music', 'party song', 'party songs',
    ],
    # ── Sad ──────────────────────────────────────────────────────────────────
    'sad': [
        'emotional', 'emotional song', 'heartbreak', 'heartbroken',
        'pain', 'painful', 'crying', 'breakup', 'break up',
        'sad song', 'sad songs', 'sad music',
    ],
    # ── Film / Soundtrack ────────────────────────────────────────────────────
    'film': [
        'soundtrack', 'ost', 'film music', 'movie song', 'movie songs',
        'film song', 'film songs', 'cinema', 'movie soundtrack',
        'background score', 'bgm',
    ],
    # ── Ghazal ───────────────────────────────────────────────────────────────
    'ghazal': [
        'ghazal music', 'ghazals',
    ],
    # ── Funk ─────────────────────────────────────────────────────────────────
    'funk': [
        'funk music', 'funky', 'disco', 'disco music',
    ],
    # ── Blues ─────────────────────────────────────────────────────────────────
    'blues': [
        'blues music', 'blues song', 'delta blues', 'chicago blues',
        'electric blues',
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
#  ARTIST NORMALIZATION RULES
#  Common patterns for cleaning up artist names.
# ═══════════════════════════════════════════════════════════════════════════════
ARTIST_ALIASES = {
    # Add known artist variations here as needed.
    # 'canonical_name': ['variation1', 'variation2', ...],
    'arijit singh': ['arijit', 'arijit sing', 'arjit singh', 'arjit sing'],
    'a.r. rahman': ['ar rahman', 'a r rahman', 'a. r. rahman', 'arrahman', 'arr', 'a.r.rahman'],
    'anirudh ravichander': ['anirudh', 'anirudh ravichandran', 'anirudh ravichander'],
    'shreya ghoshal': ['shreya ghosal', 'shreyaghoshal'],
    'lata mangeshkar': ['lata', 'lata mangeshker'],
    'kishore kumar': ['kishor kumar', 'kishore'],
    'neha kakkar': ['neha kakar', 'neha kakker'],
    'badshah': ['badsha'],
    'yo yo honey singh': ['honey singh', 'yo yo honey sing', 'yoyo honey singh'],
    'sonu nigam': ['sonu nigaam'],
    'jubin nautiyal': ['jubin nautyal', 'jubin'],
    'atif aslam': ['atif', 'aatif aslam'],
    'ed sheeran': ['ed sheran', 'ed sheerain'],
    'taylor swift': ['taylorswift'],
    'the weeknd': ['weeknd', 'the weekend'],
    'billie eilish': ['billie elish', 'billy eilish'],
    'dua lipa': ['dualipa'],
    'bts': ['방탄소년단', 'bangtan sonyeondan'],
    'blackpink': ['블랙핑크', 'black pink'],
}


# ═══════════════════════════════════════════════════════════════════════════════
#  BUILD REVERSE LOOKUP TABLES (alias → canonical)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_lookup(alias_map):
    """Build a reverse dict: every alias (lowercase) → canonical name."""
    lookup = {}
    for canonical, aliases in alias_map.items():
        canonical_lower = canonical.lower().strip()
        lookup[canonical_lower] = canonical_lower
        for alias in aliases:
            lookup[alias.lower().strip()] = canonical_lower
    return lookup

_LANG_LOOKUP = _build_lookup(LANGUAGE_ALIASES)
_GENRE_LOOKUP = _build_lookup(GENRE_ALIASES)
_ARTIST_LOOKUP = _build_lookup(ARTIST_ALIASES)


# ═══════════════════════════════════════════════════════════════════════════════
#  NORMALIZATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_language(raw):
    """Normalize a raw language value to its canonical form."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if not cleaned:
        return None

    # Direct lookup
    if cleaned in _LANG_LOOKUP:
        return _LANG_LOOKUP[cleaned]

    # Fuzzy: check if any alias is contained within the value
    for alias, canonical in sorted(_LANG_LOOKUP.items(), key=lambda x: -len(x[0])):
        if len(alias) >= 3 and alias in cleaned:
            return canonical

    return cleaned  # Return as-is if no match (already lowercased)


def normalize_genre(raw):
    """Normalize a raw genre value to its canonical form."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if not cleaned:
        return None

    # Direct lookup
    if cleaned in _GENRE_LOOKUP:
        return _GENRE_LOOKUP[cleaned]

    # Fuzzy: check if any alias is contained within the value
    for alias, canonical in sorted(_GENRE_LOOKUP.items(), key=lambda x: -len(x[0])):
        if len(alias) >= 3 and alias in cleaned:
            return canonical

    return cleaned


def normalize_artist(raw):
    """Normalize an artist name: trim, title-case, map known aliases."""
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None

    lower = cleaned.lower()

    # Skip non-useful values
    if lower in ('unknown', 'unknown artist', 'unknown channel',
                 'various artists', 'various', 'na', 'n/a', ''):
        return None

    # Check alias map
    if lower in _ARTIST_LOOKUP:
        # Return in title case
        return _ARTIST_LOOKUP[lower].title()

    # General cleanup: collapse whitespace, title-case
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Remove " - Topic" suffix (YouTube auto-generated channels)
    cleaned = re.sub(r'\s*-\s*Topic$', '', cleaned, flags=re.IGNORECASE).strip()

    return cleaned if cleaned else None


def normalize_tags(tags_json):
    """Normalize the JSON tags list — deduplicate and clean."""
    if not tags_json:
        return tags_json
    try:
        tags = json.loads(tags_json)
        if not isinstance(tags, list):
            return tags_json
        # Lowercase, strip, deduplicate while preserving order
        seen = set()
        clean = []
        for tag in tags:
            t = str(tag).strip().lower()
            if t and t not in seen:
                seen.add(t)
                clean.append(t)
        return json.dumps(clean)
    except (json.JSONDecodeError, TypeError):
        return tags_json


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Normalize metadata in the downloads table')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without writing to DB')
    parser.add_argument('--stats', action='store_true',
                        help='Show distribution stats and exit')
    args = parser.parse_args()

    from app import create_app
    app = create_app()

    with app.app_context():
        from app.models import db, Download

        # ── Stats mode ───────────────────────────────────────────────────────
        if args.stats:
            print('\n📊 Current metadata distribution:\n')

            # Languages
            langs = db.session.execute(
                db.text("SELECT language, COUNT(*) as cnt FROM downloads "
                        "WHERE language IS NOT NULL GROUP BY language ORDER BY cnt DESC")
            ).fetchall()
            print(f'  Languages ({len(langs)} unique):')
            for lang, cnt in langs:
                norm = normalize_language(lang)
                flag = f' → {norm}' if norm != lang else ''
                print(f'    {lang:20s} {cnt:4d}{flag}')

            # Genres
            genres = db.session.execute(
                db.text("SELECT genre, COUNT(*) as cnt FROM downloads "
                        "WHERE genre IS NOT NULL GROUP BY genre ORDER BY cnt DESC")
            ).fetchall()
            print(f'\n  Genres ({len(genres)} unique):')
            for genre, cnt in genres:
                norm = normalize_genre(genre)
                flag = f' → {norm}' if norm != genre else ''
                print(f'    {genre:20s} {cnt:4d}{flag}')

            # Top artists
            artists = db.session.execute(
                db.text("SELECT artist, COUNT(*) as cnt FROM downloads "
                        "WHERE artist IS NOT NULL GROUP BY artist ORDER BY cnt DESC LIMIT 30")
            ).fetchall()
            print(f'\n  Top 30 Artists:')
            for artist, cnt in artists:
                norm = normalize_artist(artist)
                flag = f' → {norm}' if norm and norm != artist else ''
                print(f'    {artist:30s} {cnt:4d}{flag}')

            print()
            return

        # ── Normalize mode ───────────────────────────────────────────────────
        songs = Download.query.all()
        print(f'\n🔧 Normalizing metadata for {len(songs)} song(s)...\n')

        lang_changes = 0
        genre_changes = 0
        artist_changes = 0
        tag_changes = 0

        for song in songs:
            changed = False

            # Language
            if song.language:
                new_lang = normalize_language(song.language)
                if new_lang and new_lang != song.language:
                    if args.dry_run:
                        print(f'  Language: "{song.language}" → "{new_lang}"  ({song.title[:40]})')
                    song.language = new_lang
                    lang_changes += 1
                    changed = True

            # Genre
            if song.genre:
                new_genre = normalize_genre(song.genre)
                if new_genre and new_genre != song.genre:
                    if args.dry_run:
                        print(f'  Genre:    "{song.genre}" → "{new_genre}"  ({song.title[:40]})')
                    song.genre = new_genre
                    genre_changes += 1
                    changed = True

            # Artist
            if song.artist:
                new_artist = normalize_artist(song.artist)
                if new_artist and new_artist != song.artist:
                    if args.dry_run:
                        print(f'  Artist:   "{song.artist}" → "{new_artist}"  ({song.title[:40]})')
                    song.artist = new_artist
                    artist_changes += 1
                    changed = True

            # Tags
            if song.tags:
                new_tags = normalize_tags(song.tags)
                if new_tags != song.tags:
                    song.tags = new_tags
                    tag_changes += 1
                    changed = True

        # ── Summary ──────────────────────────────────────────────────────────
        total = lang_changes + genre_changes + artist_changes + tag_changes
        print(f'\n{"─" * 50}')
        print(f'  Language changes:  {lang_changes}')
        print(f'  Genre changes:     {genre_changes}')
        print(f'  Artist changes:    {artist_changes}')
        print(f'  Tag changes:       {tag_changes}')
        print(f'  Total changes:     {total}')

        if args.dry_run:
            print(f'\n  (DRY RUN — no changes saved)')
            db.session.rollback()
        elif total > 0:
            db.session.commit()
            print(f'\n  ✅ All changes committed to DB!')
        else:
            print(f'\n  ✅ Everything is already normalized!')

        print()


if __name__ == '__main__':
    main()
