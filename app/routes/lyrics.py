"""
Lyrics Routes — Multi-source lyrics fetching.
Provides a backend fallback for songs not found on LRCLIB.
Sources: Genius (web scraping, no API key needed).
"""

import re
import requests
from flask import Blueprint, jsonify, request as flask_request
from bs4 import BeautifulSoup

bp = Blueprint('lyrics', __name__)

# Reusable session for connection pooling
_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
})


@bp.route('/api/lyrics', methods=['GET'])
def get_lyrics():
    """
    Fetch lyrics from Genius as a fallback.
    Query params: title (required), artist (optional)
    Returns: { plain: "...", source: "genius" } or { error: "..." }
    """
    title = flask_request.args.get('title', '').strip()
    artist = flask_request.args.get('artist', '').strip()

    if not title:
        return jsonify({'error': 'title parameter is required'}), 400

    try:
        lyrics = _search_genius(title, artist)
        if lyrics:
            return jsonify({'plain': lyrics, 'source': 'genius'})

        return jsonify({'plain': None, 'source': None})
    except Exception as e:
        return jsonify({'error': f'Lyrics fetch failed: {str(e)}'}), 500


def _search_genius(title, artist=''):
    """
    Search Genius for lyrics by scraping search results + lyrics page.
    No API key needed.
    """
    # Build search query
    query = f'{artist} {title}'.strip() if artist else title
    query = _clean_query(query)

    try:
        # Step 1: Search Genius
        search_url = 'https://genius.com/api/search/multi'
        params = {'q': query}
        resp = _session.get(search_url, params=params, timeout=8)
        if resp.status_code != 200:
            return None

        data = resp.json()
        # Find the first song hit
        song_url = _extract_song_url(data)
        if not song_url:
            return None

        # Step 2: Fetch the lyrics page
        page_resp = _session.get(song_url, timeout=8)
        if page_resp.status_code != 200:
            return None

        # Step 3: Parse lyrics from HTML
        lyrics = _parse_genius_lyrics(page_resp.text)
        return lyrics

    except (requests.RequestException, ValueError, KeyError):
        return None


def _extract_song_url(data):
    """Extract the first song URL from Genius API search response."""
    try:
        sections = data.get('response', {}).get('sections', [])
        for section in sections:
            if section.get('type') == 'song':
                hits = section.get('hits', [])
                if hits:
                    return hits[0]['result']['url']
        # Fallback: try any section with hits
        for section in sections:
            hits = section.get('hits', [])
            for hit in hits:
                result = hit.get('result', {})
                if result.get('url') and 'genius.com' in result['url']:
                    return result['url']
    except (KeyError, IndexError, TypeError):
        pass
    return None


def _parse_genius_lyrics(html):
    """
    Extract lyrics text from a Genius song page.
    Genius uses data-lyrics-container divs.
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Genius wraps lyrics in div[data-lyrics-container="true"]
    containers = soup.select('div[data-lyrics-container="true"]')
    if not containers:
        return None

    lyrics_parts = []
    for container in containers:
        # Replace <br> tags with newlines
        for br in container.find_all('br'):
            br.replace_with('\n')

        text = container.get_text(separator='')
        if text.strip():
            lyrics_parts.append(text.strip())

    lyrics = '\n'.join(lyrics_parts)

    # Clean Genius metadata junk from the beginning:
    # e.g. "10 ContributorsTranslationsहिन्दी (Hindi)Artist - Song Title Lyrics"
    # Strip "N Contributors" prefix
    lyrics = re.sub(r'^\d+\s*Contributors?', '', lyrics, flags=re.IGNORECASE).strip()
    # Strip "Translations..." line with optional language names
    lyrics = re.sub(r'^Translations[^\n]*\n?', '', lyrics, flags=re.IGNORECASE).strip()
    # Strip song title + " Lyrics" header (e.g. "Artist - Song Title Lyrics")
    lyrics = re.sub(r'^[^\n]*\bLyrics\s*\n?', '', lyrics, count=1).strip()
    # Strip "You might also like" injected by Genius
    lyrics = re.sub(r'You might also like', '', lyrics).strip()
    # Strip "See .* live" promotions
    lyrics = re.sub(r'See [^\n]* live[^\n]*', '', lyrics).strip()
    # Strip inline "Read More" artifacts
    lyrics = re.sub(r'[^\n]*Read More\s*', '', lyrics).strip()
    # Strip trailing "Embed" text
    lyrics = re.sub(r'\d*Embed$', '', lyrics).strip()

    # Clean up: remove excessive blank lines
    lyrics = re.sub(r'\n{3,}', '\n\n', lyrics)

    return lyrics.strip() if lyrics.strip() else None


def _clean_query(query):
    """Clean YouTube-style noise from search query."""
    # Strip common YouTube suffixes
    query = re.sub(
        r'\s*[\(\[]\s*(Official\s*)?(Music\s*)?(Video|Audio|Lyric|Lyrics|'
        r'Visualizer|MV|HQ|HD|4K|Live)?\s*[\)\]]',
        '', query, flags=re.IGNORECASE
    )
    # Strip "feat." sections
    query = re.sub(r'\s*[\(\[]\s*feat\.?\s+[^\)\]]+[\)\]]', '', query, flags=re.IGNORECASE)
    # Strip pipe separator junk
    query = re.sub(r'\s*\|.*$', '', query)
    # Collapse whitespace
    query = re.sub(r'\s{2,}', ' ', query).strip()
    return query
