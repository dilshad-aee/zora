"""
Normalization service — clean up inconsistent language, genre, and artist data.

Maps all variations (ISO codes, typos, abbreviations, native scripts)
to a single canonical form.
"""

import json
import re


# ═══════════════════════════════════════════════════════════════════════════════
#  LANGUAGE ALIAS MAP
#  canonical name → list of aliases (ISO codes, native script, variations)
# ═══════════════════════════════════════════════════════════════════════════════
LANGUAGE_ALIASES = {
    'hindi': [
        'hi', 'hin', 'hind', 'hindhi', 'hidi', 'hinid',
        'bollywood', 'हिन्दी', 'हिंदी', 'hindi song', 'hindi songs',
        'hindi music', 'hindi pop', 'hindi rap', 'indian',
    ],
    'tamil': [
        'ta', 'tam', 'tamizh', 'thamizh', 'தமிழ்', 'தமிழ',
        'kollywood', 'tamil song', 'tamil songs', 'tamil music',
    ],
    'telugu': [
        'te', 'tel', 'తెలుగు', 'tollywood', 'telugu song', 'telugu songs',
        'telugu music',
    ],
    'malayalam': [
        'ml', 'mal', 'mlm', 'മലയാളം', 'mollywood',
        'malayalam song', 'malayalam songs', 'malayalam music',
    ],
    'kannada': [
        'kn', 'kan', 'ಕನ್ನಡ', 'sandalwood',
        'kannada song', 'kannada songs', 'kannada music',
    ],
    'bengali': [
        'bn', 'ben', 'bangla', 'বাংলা', 'bangali',
        'bengali song', 'bengali songs', 'bengali music',
    ],
    'punjabi': [
        'pa', 'pan', 'panjabi', 'ਪੰਜਾਬੀ', 'پنجابی',
        'punjabi song', 'punjabi songs', 'punjabi music',
    ],
    'marathi': [
        'mr', 'mar', 'मराठी', 'marathi song', 'marathi songs',
    ],
    'gujarati': [
        'gu', 'guj', 'ગુજરાતી', 'gujarati song', 'gujarati songs',
    ],
    'urdu': [
        'ur', 'urd', 'اردو', 'urdu song', 'urdu songs',
    ],
    'english': [
        'en', 'eng', 'en-us', 'en-gb', 'en-au', 'en-in',
        'english song', 'english songs', 'english music',
        'pop music', 'billboard', 'western',
    ],
    'korean': [
        'ko', 'kor', 'k-pop', 'kpop', '한국어', '한국',
        'korean song', 'korean songs', 'korean music',
    ],
    'japanese': [
        'ja', 'jpn', 'j-pop', 'jpop', '日本語', '日本',
        'japanese song', 'japanese songs', 'japanese music', 'anime',
    ],
    'spanish': [
        'es', 'spa', 'español', 'espanol', 'castellano',
        'latino', 'reggaeton', 'latin',
        'spanish song', 'spanish songs', 'spanish music',
    ],
    'arabic': [
        'ar', 'ara', 'عربي', 'العربية',
        'arabic song', 'arabic songs', 'arabic music',
    ],
    'french': [
        'fr', 'fra', 'fre', 'français', 'francais',
        'french song', 'french songs', 'french music',
    ],
    'portuguese': [
        'pt', 'por', 'pt-br', 'português', 'portugues',
        'brazilian', 'portuguese song',
    ],
    'russian': [
        'ru', 'rus', 'русский', 'russian song', 'russian songs',
    ],
    'german': [
        'de', 'deu', 'ger', 'deutsch', 'german song', 'german songs',
    ],
    'chinese': [
        'zh', 'zho', 'chi', 'zh-hans', 'zh-hant', 'zh-cn', 'zh-tw',
        '中文', '中国', 'mandarin', 'cantonese', 'cpop', 'c-pop',
        'chinese song', 'chinese songs',
    ],
    'turkish': [
        'tr', 'tur', 'türkçe', 'turkce', 'turkish song',
    ],
    'italian': [
        'it', 'ita', 'italiano', 'italian song',
    ],
    'thai': [
        'th', 'tha', 'ภาษาไทย', 'thai song',
    ],
    'vietnamese': [
        'vi', 'vie', 'tiếng việt', 'vietnamese song',
    ],
    'indonesian': [
        'id', 'ind', 'bahasa indonesia', 'indonesian song',
    ],
    'nepali': [
        'ne', 'nep', 'नेपाली', 'nepali song',
    ],
    'bhojpuri': [
        'bho', 'bhojpuri song', 'bhojpuri songs', 'bhojpuri music',
    ],
    'malay': [
        'ms', 'msa', 'may', 'bahasa melayu', 'malay song',
    ],
    'sinhala': [
        'si', 'sin', 'sinhalese', 'සිංහල', 'sinhala song',
    ],
    'assamese': [
        'as', 'asm', 'অসমীয়া', 'assamese song',
    ],
    'odia': [
        'or', 'ori', 'oriya', 'ଓଡ଼ିଆ', 'odia song',
    ],
    'haryanvi': [
        'haryanvi song', 'haryanvi songs', 'haryanvi music',
    ],
    'rajasthani': [
        'rajasthani song', 'rajasthani songs', 'rajasthani music',
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
#  GENRE ALIAS MAP
# ═══════════════════════════════════════════════════════════════════════════════
GENRE_ALIASES = {
    'pop': [
        'pop music', 'pop song', 'pop songs', 'pop rock',
        'synthpop', 'synth-pop', 'electropop', 'dance pop', 'dance-pop',
        'teen pop', 'bubblegum pop', 'art pop',
    ],
    'rock': [
        'rock music', 'rock song', 'alternative rock', 'alt rock',
        'alt-rock', 'indie rock', 'classic rock', 'soft rock',
        'hard rock', 'punk rock', 'punk', 'post-punk', 'grunge',
        'progressive rock', 'prog rock', 'psychedelic rock',
        'garage rock', 'blues rock',
    ],
    'hip-hop': [
        'hip hop', 'hiphop', 'hip-hop music', 'rap', 'rap music',
        'trap', 'trap music', 'mumble rap', 'gangsta rap',
        'conscious rap', 'boom bap', 'old school hip hop',
        'underground hip hop', 'desi hip hop', 'indian hip hop',
        'gully rap',
    ],
    'r&b': [
        'rnb', 'r and b', 'r & b', 'rhythm and blues',
        'soul', 'soul music', 'neo-soul', 'neo soul',
        'contemporary r&b', 'urban contemporary',
    ],
    'electronic': [
        'edm', 'electronic music', 'electronic dance music',
        'house', 'house music', 'deep house', 'tech house',
        'techno', 'trance', 'dubstep', 'drum and bass', 'dnb',
        'd&b', 'drum & bass', 'hardstyle', 'psytrance',
        'progressive house', 'electro house', 'future bass',
        'synthwave', 'retrowave', 'electronica',
    ],
    'lo-fi': [
        'lofi', 'lo fi', 'lo-fi hip hop', 'lofi hip hop',
        'chillhop', 'study beats', 'lofi beats',
        'lo-fi beats', 'lofi music', 'lo-fi music',
        'chill beats', 'study music',
    ],
    'classical': [
        'classical music', 'carnatic', 'carnatic music',
        'hindustani', 'hindustani classical', 'raag', 'raga',
        'orchestra', 'orchestral', 'symphony', 'chamber music',
        'semi-classical', 'semi classical', 'indian classical',
    ],
    'jazz': [
        'jazz music', 'smooth jazz', 'bebop', 'swing',
        'jazz fusion', 'acid jazz', 'cool jazz', 'free jazz',
        'nu jazz', 'vocal jazz',
    ],
    'romantic': [
        'romance', 'love song', 'love songs', 'love',
        'love music', 'romantic song', 'romantic songs',
        'romantic music', 'melody', 'melodious',
    ],
    'devotional': [
        'bhajan', 'bhakti', 'devotional song', 'devotional songs',
        'worship', 'gospel', 'gospel music', 'spiritual',
        'kirtan', 'mantra', 'aarti', 'arti', 'qawwali',
        'sufi', 'sufi music', 'religious',
    ],
    'folk': [
        'folk music', 'folk song', 'folk songs', 'acoustic folk',
        'folk rock', 'indian folk', 'desi folk',
    ],
    'indie': [
        'indie music', 'indie pop', 'indie folk', 'indie electronic',
        'independent', 'independent music',
    ],
    'metal': [
        'heavy metal', 'death metal', 'metalcore', 'black metal',
        'thrash metal', 'power metal', 'doom metal', 'nu metal',
        'nu-metal', 'progressive metal', 'symphonic metal',
        'deathcore', 'metal music',
    ],
    'country': [
        'country music', 'country song', 'country songs',
        'nashville', 'country rock', 'country pop',
        'americana', 'bluegrass',
    ],
    'reggae': [
        'reggae music', 'dancehall', 'ska', 'dub', 'roots reggae',
        'reggaeton',
    ],
    'chill': [
        'ambient', 'ambient music', 'relaxing', 'relaxing music',
        'calm', 'calm music', 'peaceful', 'meditation', 'zen',
        'sleep music', 'nature sounds', 'asmr',
    ],
    'workout': [
        'gym', 'gym music', 'fitness', 'fitness music',
        'motivation', 'motivational', 'pump up', 'power music',
        'workout music', 'exercise',
    ],
    'party': [
        'dance', 'dance music', 'club', 'club music',
        'dj mix', 'dj', 'party music', 'party song', 'party songs',
    ],
    'sad': [
        'emotional', 'emotional song', 'heartbreak', 'heartbroken',
        'pain', 'painful', 'crying', 'breakup', 'break up',
        'sad song', 'sad songs', 'sad music',
    ],
    'film': [
        'soundtrack', 'ost', 'film music', 'movie song', 'movie songs',
        'film song', 'film songs', 'cinema', 'movie soundtrack',
        'background score', 'bgm',
    ],
    'ghazal': [
        'ghazal music', 'ghazals',
    ],
    'funk': [
        'funk music', 'funky', 'disco', 'disco music',
    ],
    'blues': [
        'blues music', 'blues song', 'delta blues', 'chicago blues',
        'electric blues',
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
#  ARTIST ALIAS MAP
# ═══════════════════════════════════════════════════════════════════════════════
ARTIST_ALIASES = {
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
#  LANGUAGE / GENRE KEYWORD DETECTION (from tags, title, description)
# ═══════════════════════════════════════════════════════════════════════════════

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

    if cleaned in _LANG_LOOKUP:
        return _LANG_LOOKUP[cleaned]

    for alias, canonical in sorted(_LANG_LOOKUP.items(), key=lambda x: -len(x[0])):
        if len(alias) >= 3 and alias in cleaned:
            return canonical

    return cleaned


def normalize_genre(raw):
    """Normalize a raw genre value to its canonical form."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if not cleaned:
        return None

    if cleaned in _GENRE_LOOKUP:
        return _GENRE_LOOKUP[cleaned]

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

    if lower in ('unknown', 'unknown artist', 'unknown channel',
                 'various artists', 'various', 'na', 'n/a', ''):
        return None

    if lower in _ARTIST_LOOKUP:
        return _ARTIST_LOOKUP[lower].title()

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\s*-\s*Topic$', '', cleaned, flags=re.IGNORECASE).strip()

    return cleaned if cleaned else None


# ═══════════════════════════════════════════════════════════════════════════════
#  DETECTION HELPERS (extract metadata from yt-dlp info dicts)
# ═══════════════════════════════════════════════════════════════════════════════

def detect_language(tags, title, description=''):
    """Detect language from tags, title, and description using keyword matching."""
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
    """Detect genre from tags, title, and description using keyword matching."""
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


def extract_and_normalize_metadata(info):
    """
    Extract language, genre, and artist from a yt-dlp info dict,
    then normalize all three values.

    Returns a dict with keys: language, genre, artist.
    """
    tags = info.get('tags') or []
    categories = info.get('categories') or []
    all_tags = [str(t).lower().strip() for t in list(tags) + list(categories) if t]

    title = info.get('title') or ''
    description = info.get('description') or ''

    # Language: prefer yt-dlp's raw value, fall back to keyword detection
    lang_raw = info.get('language') or ''
    lang = lang_raw or detect_language(all_tags, title, description)
    lang = normalize_language(lang) if lang else None

    # Genre: prefer yt-dlp's raw value, fall back to keyword detection
    genre_raw = info.get('genre') or ''
    genre = genre_raw or detect_genre(all_tags, title, description)
    genre = normalize_genre(genre) if genre else None

    # Artist
    artist_raw = info.get('artist') or info.get('uploader') or ''
    artist = normalize_artist(artist_raw) if artist_raw else None

    return {
        'language': lang,
        'genre': genre,
        'artist': artist,
    }
