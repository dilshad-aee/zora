"""
Spotify Import routes — submit, status, list jobs, and save as playlist.
All routes are admin-only.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.auth.decorators import admin_required

bp = Blueprint('spotify_import', __name__)


@bp.route('/start', methods=['POST'])
@admin_required
def start_import():
    """Start a Spotify playlist import job."""
    from app.services.spotify_import_service import spotify_import_service
    from flask import current_app

    data = request.get_json(silent=True) or {}
    playlist_url = data.get('playlist_url', '').strip()

    if not playlist_url:
        return jsonify({'error': 'playlist_url is required'}), 400

    try:
        app = current_app._get_current_object()
        result = spotify_import_service.start_job(
            playlist_url=playlist_url,
            user_id=current_user.id,
            app=app,
        )
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to start import: {str(e)}'}), 500


@bp.route('/status/<job_id>', methods=['GET'])
@admin_required
def get_status(job_id):
    """Get import job status with per-track details."""
    from app.services.spotify_import_service import spotify_import_service

    result = spotify_import_service.get_job_status(job_id)
    if not result:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(result)


@bp.route('/jobs', methods=['GET'])
@admin_required
def list_jobs():
    """List recent import jobs for current user."""
    from app.services.spotify_import_service import spotify_import_service

    jobs = spotify_import_service.get_user_jobs(current_user.id)
    return jsonify({'jobs': jobs})


@bp.route('/save-playlist/<job_id>', methods=['POST'])
@admin_required
def save_as_playlist(job_id):
    """Create a playlist from all successfully downloaded tracks in a job."""
    from app.models import db, Playlist, PlaylistSong, Download
    from app.models import SpotifyImportJob, SpotifyImportTrack

    job = SpotifyImportJob.query.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    data = request.get_json(silent=True) or {}
    playlist_name = data.get('name', '').strip() or job.playlist_name or 'Spotify Import'

    # Get all downloaded tracks with video_ids
    downloaded_tracks = SpotifyImportTrack.query.filter_by(
        job_id=job_id,
        status='downloaded',
    ).all()

    if not downloaded_tracks:
        return jsonify({'error': 'No downloaded tracks to save'}), 400

    # Create playlist
    playlist = Playlist(
        name=playlist_name,
        description=f'Imported from Spotify: {job.playlist_url}',
        owner_user_id=current_user.id,
        visibility='private',
    )
    db.session.add(playlist)
    db.session.flush()

    # Find matching downloads by video_id and add to playlist
    added = 0
    for track in downloaded_tracks:
        if not track.video_id:
            continue

        download = Download.query.filter_by(video_id=track.video_id).first()
        if not download:
            continue

        # Check if already in this playlist
        exists = PlaylistSong.query.filter_by(
            playlist_id=playlist.id,
            download_id=download.id,
        ).first()
        if exists:
            continue

        ps = PlaylistSong(
            playlist_id=playlist.id,
            download_id=download.id,
        )
        db.session.add(ps)
        added += 1

    db.session.commit()

    return jsonify({
        'playlist': playlist.to_dict(),
        'tracks_added': added,
    }), 201
