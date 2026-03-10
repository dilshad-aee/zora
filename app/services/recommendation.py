"""
Recommendation Engine - generates personalized feed of song sets
using content-based matching + engagement scoring.
"""

from datetime import datetime, timedelta

from app.models import db, Download, SongLike, PlayEvent, UserTaste


class RecommendationEngine:
    """Generates personalized song set feeds for users."""

    def _build_taste_profile(self, user_id):
        """Build weighted preference maps from onboarding + behavior."""
        w_language = {}
        w_genre = {}
        w_artist = {}

        # A) Onboarding prefs: +3 each
        taste = UserTaste.query.filter_by(user_id=user_id).first()
        if taste and taste.onboarding_completed:
            for lang in taste.get_languages():
                w_language[lang] = w_language.get(lang, 0) + 3
            for genre in taste.get_genres():
                w_genre[genre] = w_genre.get(genre, 0) + 3
            for artist in taste.get_artists():
                w_artist[artist.lower()] = w_artist.get(artist.lower(), 0) + 3

        # B) Liked songs: +5 for each attribute
        liked_ids = {sl.download_id for sl in SongLike.query.filter_by(user_id=user_id).all()}
        if liked_ids:
            liked_songs = Download.query.filter(Download.id.in_(liked_ids)).all()
            for song in liked_songs:
                if song.language:
                    w_language[song.language] = w_language.get(song.language, 0) + 5
                if song.genre:
                    w_genre[song.genre] = w_genre.get(song.genre, 0) + 5
                if song.artist:
                    w_artist[song.artist.lower()] = w_artist.get(song.artist.lower(), 0) + 5

        # C) Play events: +2 for completed, +1 for partial (>30s)
        play_summary = db.session.query(
            PlayEvent.download_id,
            db.func.count(PlayEvent.id).label('plays'),
            db.func.sum(db.case((PlayEvent.completed == True, 1), else_=0)).label('completions'),
        ).filter_by(user_id=user_id).group_by(PlayEvent.download_id).all()

        played_song_ids = {ps.download_id for ps in play_summary}
        if played_song_ids:
            played_songs = {s.id: s for s in Download.query.filter(Download.id.in_(played_song_ids)).all()}
            for ps in play_summary:
                song = played_songs.get(ps.download_id)
                if not song:
                    continue
                weight = min(ps.completions * 2 + max(0, ps.plays - ps.completions), 10)
                if song.language:
                    w_language[song.language] = w_language.get(song.language, 0) + weight
                if song.genre:
                    w_genre[song.genre] = w_genre.get(song.genre, 0) + weight
                if song.artist:
                    w_artist[song.artist.lower()] = w_artist.get(song.artist.lower(), 0) + weight

        return w_language, w_genre, w_artist

    def _score_song(self, song, w_language, w_genre, w_artist):
        """Content match score for a song."""
        score = 0.0
        if song.language:
            score += 2.0 * w_language.get(song.language, 0)
        if song.genre:
            score += 1.5 * w_genre.get(song.genre, 0)
        if song.artist:
            score += 2.5 * w_artist.get(song.artist.lower(), 0)
        return score

    def generate_feed(self, user_id, max_sets=6, set_size=12):
        """Generate personalized feed of song sets."""
        all_songs = Download.query.all()
        liked_ids = {sl.download_id for sl in SongLike.query.filter_by(user_id=user_id).all()}

        # Play stats per song for this user
        play_stats = {}
        play_rows = db.session.query(
            PlayEvent.download_id,
            db.func.count(PlayEvent.id).label('plays'),
            db.func.sum(db.case((PlayEvent.completed == True, 1), else_=0)).label('completions'),
            db.func.max(PlayEvent.started_at).label('last_played'),
        ).filter_by(user_id=user_id).group_by(PlayEvent.download_id).all()
        for row in play_rows:
            play_stats[row.download_id] = {
                'plays': row.plays,
                'completions': row.completions or 0,
                'last_played': row.last_played,
            }

        w_language, w_genre, w_artist = self._build_taste_profile(user_id)

        used_ids = set()
        sets = []

        def _make_song_dict(song):
            d = song.to_dict()
            d['liked'] = song.id in liked_ids
            stats = play_stats.get(song.id, {})
            d['play_count'] = stats.get('plays', 0)
            return d

        def _add_set(key, title, songs, emoji=''):
            nonlocal used_ids
            unique = [s for s in songs if s.id not in used_ids][:set_size]
            if not unique:
                return
            used_ids.update(s.id for s in unique)
            sets.append({
                'key': key,
                'title': f'{emoji} {title}'.strip(),
                'songs': [_make_song_dict(s) for s in unique],
            })

        # SET 1: Most Played (engagement-based)
        most_played_ids = sorted(
            play_stats.keys(),
            key=lambda did: play_stats[did]['plays'] + play_stats[did]['completions'] * 2,
            reverse=True,
        )[:set_size]
        most_played_songs = [s for s in all_songs if s.id in most_played_ids]
        most_played_songs.sort(
            key=lambda s: play_stats.get(s.id, {}).get('plays', 0) + play_stats.get(s.id, {}).get('completions', 0) * 2,
            reverse=True,
        )
        if most_played_songs:
            _add_set('most_played', 'Most Played', most_played_songs, '🔥')

        # SET 2: Your Favorites (liked songs, newest first)
        liked_songs = sorted(
            [s for s in all_songs if s.id in liked_ids],
            key=lambda s: s.downloaded_at or datetime.min,
            reverse=True,
        )
        if liked_songs:
            _add_set('favorites', 'Your Favorites', liked_songs, '❤️')

        # SET 3: Recently Added
        recently_added = sorted(all_songs, key=lambda s: s.downloaded_at or datetime.min, reverse=True)
        _add_set('recently_added', 'Recently Added', recently_added, '🆕')

        # SET 4-5: Top language sets (from taste profile)
        top_languages = sorted(w_language.keys(), key=lambda l: w_language[l], reverse=True)[:2]
        for lang in top_languages:
            lang_songs = [s for s in all_songs if s.language == lang]
            lang_songs.sort(
                key=lambda s: self._score_song(s, w_language, w_genre, w_artist) + play_stats.get(s.id, {}).get('plays', 0) * 0.5,
                reverse=True,
            )
            display_name = lang.title()
            _add_set(f'lang_{lang}', f'{display_name} Hits', lang_songs, '🎵')

        # SET 6: Top genre set
        top_genres = sorted(w_genre.keys(), key=lambda g: w_genre[g], reverse=True)[:1]
        for genre in top_genres:
            genre_songs = [s for s in all_songs if s.genre == genre]
            genre_songs.sort(key=lambda s: self._score_song(s, w_language, w_genre, w_artist), reverse=True)
            _add_set(f'genre_{genre}', f'{genre.title()} Vibes', genre_songs, '🎧')

        # SET 7: Discover (songs user hasn't heard, ranked by content match + novelty)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recently_played_ids = {
            did for did, stats in play_stats.items()
            if stats.get('last_played') and stats['last_played'] > week_ago
        }
        discover_candidates = [s for s in all_songs if s.id not in liked_ids and s.id not in recently_played_ids]

        for s in discover_candidates:
            s._discover_score = self._score_song(s, w_language, w_genre, w_artist)
            if s.id not in play_stats:
                s._discover_score *= 1.0
            else:
                days_since = (datetime.utcnow() - (play_stats[s.id].get('last_played') or datetime.utcnow())).days
                s._discover_score *= (0.2 + 0.8 * min(1, days_since / 30))

        discover_candidates.sort(key=lambda s: getattr(s, '_discover_score', 0), reverse=True)
        if discover_candidates:
            _add_set('discover', 'Discover', discover_candidates, '✨')

        # COLD START FALLBACK: new user with no data → show recently added
        if not sets:
            _add_set(
                'recently_added', 'Recently Added',
                sorted(all_songs, key=lambda s: s.downloaded_at or datetime.min, reverse=True),
                '🆕',
            )

        return sets[:max_sets]

    @staticmethod
    def get_onboarding_options():
        """Get available languages, genres, and artists from the library for onboarding UI."""
        from sqlalchemy import func

        languages = db.session.query(
            Download.language, func.count(Download.id)
        ).filter(
            Download.language.isnot(None), Download.language != ''
        ).group_by(Download.language).order_by(func.count(Download.id).desc()).all()

        genres = db.session.query(
            Download.genre, func.count(Download.id)
        ).filter(
            Download.genre.isnot(None), Download.genre != ''
        ).group_by(Download.genre).order_by(func.count(Download.id).desc()).all()

        artists = db.session.query(
            Download.artist, func.count(Download.id)
        ).filter(
            Download.artist.isnot(None), Download.artist != '',
            ~Download.artist.in_(['Unknown', 'Unknown Artist', 'unknown'])
        ).group_by(Download.artist).order_by(func.count(Download.id).desc()).limit(50).all()

        return {
            'languages': [{'name': l[0], 'count': l[1]} for l in languages],
            'genres': [{'name': g[0], 'count': g[1]} for g in genres],
            'artists': [{'name': a[0], 'count': a[1]} for a in artists],
        }


recommendation_engine = RecommendationEngine()
