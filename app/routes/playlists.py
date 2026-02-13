"""
Playlist Routes - create playlists and manage playlist songs.
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app.models import db, Download, Playlist, PlaylistSong

bp = Blueprint('playlists', __name__)


@bp.route('/playlists', methods=['GET'])
def list_playlists():
    """Return all playlists."""
    playlists = Playlist.query.order_by(Playlist.created_at.desc()).all()
    return jsonify([playlist.to_dict() for playlist in playlists])


@bp.route('/playlists', methods=['POST'])
def create_playlist():
    """Create a new playlist."""
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()

    if not name:
        return jsonify({'error': 'Playlist name is required'}), 400

    if len(name) > 120:
        return jsonify({'error': 'Playlist name is too long'}), 400

    existing = Playlist.query.filter(func.lower(Playlist.name) == name.lower()).first()
    if existing:
        return jsonify({
            'error': 'Playlist already exists',
            'playlist': existing.to_dict(),
        }), 409

    playlist = Playlist(name=name)
    db.session.add(playlist)
    db.session.commit()
    return jsonify(playlist.to_dict()), 201


@bp.route('/playlists/<int:playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id):
    """Delete playlist and all mappings."""
    playlist = Playlist.query.get(playlist_id)
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404

    db.session.delete(playlist)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/playlists/<int:playlist_id>/songs', methods=['GET'])
def get_playlist_songs(playlist_id):
    """Return songs in a playlist."""
    playlist = Playlist.query.get(playlist_id)
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404

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
        'playlist': playlist.to_dict(),
        'songs': songs,
    })


@bp.route('/playlists/<int:playlist_id>/songs', methods=['POST'])
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

