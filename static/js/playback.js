/**
 * Zora - Playback Module
 * Playback queue, shuffle, track navigation
 * 
 * Dependencies: player.js, app.js (State), playlists.js (renderSelectedPlaylistPanel)
 *               library.js (isViewActive)
 */

// Current playback index in active queue
let currentPlayIndex = -1;
let shuffleRemainingIndices = [];

function resetShuffleRemainingIndices(excludeIndex = null) {
    const queueLength = Array.isArray(State.playback.queue) ? State.playback.queue.length : 0;
    shuffleRemainingIndices = [];

    for (let i = 0; i < queueLength; i += 1) {
        if (queueLength > 1 && Number.isFinite(excludeIndex) && i === excludeIndex) continue;
        shuffleRemainingIndices.push(i);
    }
}

function takeNextShuffleIndex() {
    const queue = State.playback.queue;
    if (!Array.isArray(queue) || queue.length === 0) return -1;

    if (queue.length === 1) {
        return Player.repeat === 'all' ? 0 : -1;
    }

    if (!Array.isArray(shuffleRemainingIndices) || shuffleRemainingIndices.length === 0) {
        if (Player.repeat !== 'all') {
            return -1;
        }
        resetShuffleRemainingIndices(currentPlayIndex);
    }

    if (!shuffleRemainingIndices.length) return -1;

    const randomPos = Math.floor(Math.random() * shuffleRemainingIndices.length);
    const [nextIndex] = shuffleRemainingIndices.splice(randomPos, 1);
    return Number.isFinite(nextIndex) ? nextIndex : -1;
}

function toPlaybackTrack(item) {
    if (!item) return null;

    const id = Number(item.id);
    const filename = item.filename || '';
    if (!filename) return null;

    return {
        id: Number.isFinite(id) ? id : null,
        filename,
        title: item.title || 'Unknown Title',
        artist: item.artist || item.uploader || 'Unknown Artist',
        thumbnail: item.thumbnail || ''
    };
}

function buildLibraryPlaybackQueue() {
    return State.downloads.map(toPlaybackTrack).filter(Boolean);
}

function buildSelectedPlaylistPlaybackQueue() {
    return State.playlists.songs.map(toPlaybackTrack).filter(Boolean);
}

function setPlaybackQueue(source, tracks, startIndex = 0, playlistId = null) {
    const queue = Array.isArray(tracks) ? tracks.filter(track => track && track.filename) : [];
    if (!queue.length) {
        State.playback.queue = [];
        State.playback.source = 'library';
        State.playback.playlistId = null;
        currentPlayIndex = -1;
        shuffleRemainingIndices = [];
        return false;
    }

    State.playback.queue = queue;
    State.playback.source = source || 'library';

    const numericPlaylistId = Number(playlistId);
    State.playback.playlistId = Number.isFinite(numericPlaylistId) && numericPlaylistId > 0
        ? numericPlaylistId
        : null;

    currentPlayIndex = Math.max(0, Math.min(startIndex, queue.length - 1));
    resetShuffleRemainingIndices(currentPlayIndex);
    return true;
}

function playFromCurrentQueue(index) {
    if (!Array.isArray(State.playback.queue) || State.playback.queue.length === 0) return;

    const safeIndex = Math.max(0, Math.min(index, State.playback.queue.length - 1));
    const track = State.playback.queue[safeIndex];
    if (!track || !track.filename) return;

    currentPlayIndex = safeIndex;
    if (Array.isArray(shuffleRemainingIndices) && shuffleRemainingIndices.length) {
        shuffleRemainingIndices = shuffleRemainingIndices.filter(
            (candidateIndex) => candidateIndex !== safeIndex
        );
    }
    Player.play(
        track.filename,
        track.title || 'Unknown',
        track.artist || 'Unknown Artist',
        track.thumbnail || ''
    );

    if (isViewActive('playlistsView')) {
        renderSelectedPlaylistPanel();
    }
}

function prunePlaybackQueueAfterDelete(downloadId, filename) {
    if (!Array.isArray(State.playback.queue) || State.playback.queue.length === 0) return;

    const currentTrack = State.playback.queue[currentPlayIndex] || null;
    State.playback.queue = State.playback.queue.filter((track) => {
        const isIdMatch = Number.isFinite(Number(track.id)) && Number(track.id) === Number(downloadId);
        const isFileMatch = filename && track.filename === filename;
        return !(isIdMatch || isFileMatch);
    });

    if (!State.playback.queue.length) {
        currentPlayIndex = -1;
        State.playback.source = 'library';
        State.playback.playlistId = null;
        shuffleRemainingIndices = [];
        return;
    }

    if (currentTrack?.filename) {
        const sameTrackIndex = State.playback.queue.findIndex(
            track => track.filename === currentTrack.filename
        );
        if (sameTrackIndex !== -1) {
            currentPlayIndex = sameTrackIndex;
            resetShuffleRemainingIndices(currentPlayIndex);
            return;
        }
    }

    currentPlayIndex = Math.min(currentPlayIndex, State.playback.queue.length - 1);
    resetShuffleRemainingIndices(currentPlayIndex);
}

function getCurrentPlaybackSongId() {
    if (currentPlayIndex < 0 || !Array.isArray(State.playback.queue)) return null;
    const track = State.playback.queue[currentPlayIndex];
    return Number.isFinite(Number(track?.id)) ? Number(track.id) : null;
}

function playTrack(filename, title, artist, thumbnail) {
    if (!filename) {
        UI.toast('Cannot play - no file found', 'error');
        return;
    }

    const libraryQueue = buildLibraryPlaybackQueue();
    const matchedIndex = libraryQueue.findIndex(track => track.filename === filename);

    if (matchedIndex !== -1 && setPlaybackQueue('library', libraryQueue, matchedIndex, null)) {
        playFromCurrentQueue(matchedIndex);
        return;
    }

    setPlaybackQueue('library', [{
        id: null,
        filename,
        title: title || 'Unknown Title',
        artist: artist || 'Unknown Artist',
        thumbnail: thumbnail || ''
    }], 0, null);
    playFromCurrentQueue(0);
}

// Play next track (called by Player when song ends)
function playNextTrack() {
    const queue = State.playback.queue;
    if (!Array.isArray(queue) || queue.length === 0) return;

    let nextIndex;

    if (Player.shuffle) {
        nextIndex = takeNextShuffleIndex();
        if (nextIndex === -1) {
            Player.showToast('End of playlist');
            return;
        }
    } else {
        // Next in order
        nextIndex = currentPlayIndex + 1;

        // End of list
        if (nextIndex >= queue.length) {
            if (Player.repeat === 'all') {
                nextIndex = 0; // Loop back to start
            } else {
                // No repeat - stop playback
                Player.showToast('End of playlist');
                return;
            }
        }
    }

    playFromCurrentQueue(nextIndex);
}

function playPreviousTrack() {
    const queue = State.playback.queue;
    if (!Array.isArray(queue) || queue.length === 0) return;

    const elapsed = Player.getCurrentTime?.() || 0;
    if (elapsed > 3 && Player.audio) {
        Player.audio.currentTime = 0;
        return;
    }

    let previousIndex;
    if (Player.shuffle) {
        do {
            previousIndex = Math.floor(Math.random() * queue.length);
        } while (previousIndex === currentPlayIndex && queue.length > 1);
    } else {
        previousIndex = currentPlayIndex - 1;
        if (previousIndex < 0) {
            if (Player.repeat === 'all') {
                previousIndex = queue.length - 1;
            } else {
                if (Player.audio) Player.audio.currentTime = 0;
                return;
            }
        }
    }

    playFromCurrentQueue(previousIndex);
}

function playTrackAtIndex(index) {
    const safeIndex = Number(index);
    if (!Number.isFinite(safeIndex)) return;
    playFromCurrentQueue(safeIndex);
}

// Make it globally accessible for Player
window.playNextTrack = playNextTrack;
window.playPreviousTrack = playPreviousTrack;
window.playTrackAtIndex = playTrackAtIndex;
