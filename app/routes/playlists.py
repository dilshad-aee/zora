"""
Playlist Routes - CRUD, explore, likes, and song management.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import func

from app.auth.decorators import owns_playlist
from app.models import db, Download, Playlist, PlaylistSong, PlaylistCategory, PlaylistLike

bp = Blueprint('playlists', __name__)


# ==================== Playlist CRUD ====================

@bp.route('/playlists', methods=['GET'])
@login_required
def list_playlists():
    """Return playlists owned by the current user."""
    query = Playlist.query.filter_by(owner_user_id=current_user.id)

    visibility = request.args.get('visibility', '').strip()
    if visibility in ('public', 'private'):
        query = query.filter_by(visibility=visibility)

    playlists = query.order_by(Playlist.created_at.desc()).all()
    return jsonify([p.to_dict(include_liked=True, current_user_id=current_user.id) for p in playlists])


@bp.route('/playlists', methods=['POST'])
@login_required
def create_playlist():
    """Create a new playlist."""
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()

    if not name:
        return jsonify({'error': 'Playlist name is required'}), 400
    if len(name) > 120:
        return jsonify({'error': 'Playlist name is too long'}), 400

    existing = Playlist.query.filter(
        func.lower(Playlist.name) == name.lower(),
        Playlist.owner_user_id == current_user.id,
    ).first()
    if existing:
        return jsonify({
            'error': 'Playlist already exists',
            'playlist': existing.to_dict(),
        }), 409

    visibility = str(data.get('visibility', 'private')).strip()
    if visibility not in ('public', 'private'):
        visibility = 'private'

    description = str(data.get('description', '')).strip()[:500]

    category_id = data.get('category_id')
    if category_id is not None:
        try:
            category_id = int(category_id)
            if not PlaylistCategory.query.get(category_id):
                category_id = None
        except (ValueError, TypeError):
            category_id = None

    playlist = Playlist(
        name=name,
        description=description,
        owner_user_id=current_user.id,
        visibility=visibility,
        category_id=category_id,
    )
    db.session.add(playlist)
    db.session.commit()
    return jsonify(playlist.to_dict(include_liked=True, current_user_id=current_user.id)), 201


@bp.route('/playlists/<int:playlist_id>', methods=['PATCH'])
@owns_playlist('playlist_id')
def update_playlist(playlist_id):
    """Update playlist metadata."""
    playlist = Playlist.query.get(playlist_id)
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = str(data['name']).strip()
        if not name:
            return jsonify({'error': 'Playlist name is required'}), 400
        if len(name) > 120:
            return jsonify({'error': 'Playlist name is too long'}), 400
        dup = Playlist.query.filter(
            func.lower(Playlist.name) == name.lower(),
            Playlist.owner_user_id == playlist.owner_user_id,
            Playlist.id != playlist_id,
        ).first()
        if dup:
            return jsonify({'error': 'A playlist with this name already exists'}), 409
        playlist.name = name

    if 'description' in data:
        playlist.description = str(data['description']).strip()[:500]

    if 'visibility' in data:
        vis = str(data['visibility']).strip()
        if vis in ('public', 'private'):
            playlist.visibility = vis

    if 'category_id' in data:
        cat_id = data['category_id']
        if cat_id is None or cat_id == '':
            playlist.category_id = None
        else:
            try:
                cat_id = int(cat_id)
                if PlaylistCategory.query.get(cat_id):
                    playlist.category_id = cat_id
            except (ValueError, TypeError):
                pass

    db.session.commit()
    return jsonify(playlist.to_dict(include_liked=True, current_user_id=current_user.id))


@bp.route('/playlists/<int:playlist_id>', methods=['DELETE'])
@owns_playlist('playlist_id')
def delete_playlist(playlist_id):
    """Delete playlist and all mappings."""
    playlist = Playlist.query.get(playlist_id)
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404

    # Delete all likes for this playlist
    PlaylistLike.query.filter_by(playlist_id=playlist_id).delete()

    db.session.delete(playlist)
    db.session.commit()
    return jsonify({'success': True})


# ==================== Explore ====================

@bp.route('/playlists/explore', methods=['GET'])
@login_required
def explore_playlists():
    """Browse public playlists with filtering and sorting."""
    query = Playlist.query.filter_by(visibility='public')

    # Category filter
    category_id = request.args.get('category', type=int)
    if category_id:
        query = query.filter_by(category_id=category_id)

    # Search
    search = request.args.get('q', '').strip()
    if search:
        pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                Playlist.name.ilike(pattern),
                Playlist.description.ilike(pattern),
            )
        )

    # Sort
    sort = request.args.get('sort', 'recent').strip()
    if sort == 'popular':
        query = query.order_by(Playlist.like_count.desc(), Playlist.created_at.desc())
    else:
        query = query.order_by(Playlist.created_at.desc())

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 50)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'playlists': [
            p.to_dict(include_liked=True, current_user_id=current_user.id)
            for p in pagination.items
        ],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
    })


# ==================== Likes ====================

@bp.route('/playlists/<int:playlist_id>/like', methods=['POST'])
@login_required
def like_playlist(playlist_id):
    """Like a playlist (idempotent)."""
    playlist = Playlist.query.get(playlist_id)
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404

    # Must be public or own playlist
    if playlist.visibility != 'public' and playlist.owner_user_id != current_user.id:
        return jsonify({'error': 'Playlist not found'}), 404

    existing = PlaylistLike.query.filter_by(
        user_id=current_user.id, playlist_id=playlist_id
    ).first()
    if existing:
        return jsonify({'liked': True, 'like_count': playlist.like_count})

    like = PlaylistLike(user_id=current_user.id, playlist_id=playlist_id)
    db.session.add(like)
    playlist.like_count = (playlist.like_count or 0) + 1
    db.session.commit()
    return jsonify({'liked': True, 'like_count': playlist.like_count}), 201


@bp.route('/playlists/<int:playlist_id>/like', methods=['DELETE'])
@login_required
def unlike_playlist(playlist_id):
    """Unlike a playlist."""
    playlist = Playlist.query.get(playlist_id)
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404

    existing = PlaylistLike.query.filter_by(
        user_id=current_user.id, playlist_id=playlist_id
    ).first()
    if not existing:
        return jsonify({'liked': False, 'like_count': playlist.like_count})

    db.session.delete(existing)
    playlist.like_count = max(0, (playlist.like_count or 0) - 1)
    db.session.commit()
    return jsonify({'liked': False, 'like_count': playlist.like_count})


# ==================== Song Management ====================

@bp.route('/playlists/<int:playlist_id>/songs', methods=['GET'])
@login_required
def get_playlist_songs(playlist_id):
    """Return songs in a playlist. Accessible if public or owned."""
    playlist = Playlist.query.get(playlist_id)
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404

    # Check access
    if playlist.visibility != 'public' and playlist.owner_user_id != current_user.id:
        if not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403

    entries = (
        PlaylistSong.query
        .filter_by(playlist_id=playlist_id)
        .order_by(PlaylistSong.added_at.desc())
        .all()
    )

    songs = []
    stale_entries = []
    for entry in entries:
        if not entry.download:
            stale_entries.append(entry)
            continue

        song_data = entry.download.to_dict()
        song_data['added_at'] = entry.added_at.isoformat() if entry.added_at else None
        songs.append(song_data)

    if stale_entries:
        for entry in stale_entries:
            db.session.delete(entry)
        db.session.commit()

    return jsonify({
        'playlist': playlist.to_dict(include_liked=True, current_user_id=current_user.id),
        'songs': songs,
        'is_owner': playlist.owner_user_id == current_user.id,
    })


@bp.route('/playlists/<int:playlist_id>/songs', methods=['POST'])
@owns_playlist('playlist_id')
def add_song_to_playlist(playlist_id):
    """Add downloaded song to a playlist."""
    playlist = Playlist.query.get(playlist_id)
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404

    data = request.get_json(silent=True) or {}
    download_id = data.get('download_id')

    try:
        download_id = int(download_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid download id'}), 400

    download = Download.query.get(download_id)
    if not download:
        return jsonify({'error': 'Song not found in downloads'}), 404

    existing = PlaylistSong.query.filter_by(
        playlist_id=playlist_id,
        download_id=download_id,
    ).first()
    if existing:
        return jsonify({'error': 'Song already in playlist'}), 409

    entry = PlaylistSong(playlist_id=playlist_id, download_id=download_id)
    db.session.add(entry)
    db.session.commit()

    return jsonify({
        'success': True,
        'song': download.to_dict(),
    }), 201


@bp.route('/playlists/<int:playlist_id>/songs/<int:download_id>', methods=['DELETE'])
@owns_playlist('playlist_id')
def remove_song_from_playlist(playlist_id, download_id):
    """Remove song from playlist."""
    entry = PlaylistSong.query.filter_by(
        playlist_id=playlist_id,
        download_id=download_id,
    ).first()

    if not entry:
        return jsonify({'error': 'Song not found in playlist'}), 404

    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})
