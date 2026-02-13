/**
 * Zora - Main Application
 * YouTube Music Downloader
 * 
 * Dependencies: api.js, player.js, ui.js
 */

// ==================== State ====================
const State = {
    mode: 'url',           // 'url', 'playlist', or 'search'
    format: 'm4a',
    quality: '320',
    currentJobId: null,
    pollInterval: null,
    currentVideo: null,
    lastDownloaded: null,
    downloads: [],
    queue: [],
    queueActive: [],
    queuePollInterval: null,
    queuePollBusy: false,
    queueJobStates: {},
    playlists: {
        items: [],
        selectedId: null,
        songs: [],
        addModalSongId: null
    },
    playback: {
        queue: [],
        source: 'library',
        playlistId: null
    },
    library: {
        batchSize: 24,
        visibleCount: 0,
        observer: null,
        scrollListenerAttached: false
    },
    playlist: {
        items: [],
        selected: new Set()
    },
    playlistSession: null,
    playlistPollInterval: null,
    playlistDownload: {
        sessionId: null,
        lastStatus: null,
        inProgress: false
    }
};

// ==================== Initialize ====================
document.addEventListener('DOMContentLoaded', () => {
    init();
});

async function init() {
    // Initialize player
    Player.init();

    // Setup event listeners
    setupEventListeners();
    setupLibraryLazyLoading();
    
    // Adjust main content padding based on player height
    adjustMainPadding();
    window.addEventListener('resize', adjustMainPadding);

    // Restore playlist download session from localStorage
    const savedSession = localStorage.getItem('playlist_download_session');
    if (savedSession) {
        State.playlistDownload.sessionId = savedSession;
        State.playlistSession = savedSession;
        startPlaylistPolling();
    }

    // Load data
    await loadSettings();
    await loadHistory();
    await loadPlaylists();
    await loadQueue();
    startQueuePolling();
}

function setupEventListeners() {
    // Enter key on search input
    const input = document.getElementById('mainInput');
    if (input) {
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleMainAction();
        });
    }
}

// ==================== Dynamic Padding for Player ====================
function adjustMainPadding() {
    const player = document.getElementById('playerBar');
    const mobileNav = document.querySelector('.mobile-nav');
    const main = document.getElementById('mainContent');
    
    if (!main) return;
    
    // Calculate total height of fixed bottom elements
    let bottomHeight = 0;
    
    if (player && !player.classList.contains('hidden')) {
        bottomHeight += player.offsetHeight;
    }
    
    if (mobileNav && window.getComputedStyle(mobileNav).display !== 'none') {
        bottomHeight += mobileNav.offsetHeight;
    }
    
    // Add extra padding for safe area and breathing room
    const extraPadding = 20;
    main.style.paddingBottom = (bottomHeight + extraPadding) + 'px';
}

// ==================== Tab Switching ====================
function switchTab(mode) {
    State.mode = mode;
    const input = document.getElementById('mainInput');
    const urlTab = document.getElementById('tabUrl');
    const playlistTab = document.getElementById('tabPlaylist');
    const searchTab = document.getElementById('tabSearch');
    const hint = document.getElementById('searchHint');

    // Reset active states
    urlTab?.classList.remove('active');
    playlistTab?.classList.remove('active');
    searchTab?.classList.remove('active');

    if (!input || !hint) return;

    if (mode === 'url') {
        urlTab?.classList.add('active');
        input.placeholder = 'Paste YouTube or YouTube Music URL here...';
        hint.innerHTML = '<i class="fas fa-info-circle"></i> Supports: youtube.com, youtu.be, music.youtube.com';
    } else if (mode === 'playlist') {
        playlistTab?.classList.add('active');
        input.placeholder = 'Paste YouTube Playlist URL here...';
        hint.innerHTML = '<i class="fas fa-list"></i> Supports: youtube.com/playlist, music.youtube.com/playlist';
    } else {
        searchTab?.classList.add('active');
        input.placeholder = 'Search for songs, artists, or albums...';
        hint.innerHTML = '<i class="fas fa-info-circle"></i> Type a song name and press Enter to search';
    }

    input.focus();
}

// ==================== Main Actions ====================
async function handleMainAction() {
    const inputEl = document.getElementById('mainInput');
    const input = inputEl?.value?.trim() ?? '';
    if (!input) {
        UI.toast('Please enter a URL or search term', 'error');
        return;
    }

    const isUrl = input.includes('youtube.com') || input.includes('youtu.be') || input.includes('music.youtube');
    const isPlaylistUrl = isUrl && (input.includes('list=') || input.includes('/playlist'));

    // If playlist tab is active but URL is a single video, gracefully fall back.
    if (State.mode === 'playlist' && isUrl && !isPlaylistUrl) {
        switchTab('url');
        UI.toast('Detected a single video URL. Switched to URL mode.', 'success');
        await fetchVideoInfo(input);
        return;
    }

    if (State.mode === 'playlist' || isPlaylistUrl) {
        await fetchPlaylistInfo(input);
    } else if (State.mode === 'url' || isUrl) {
        await fetchVideoInfo(input);
    } else {
        await searchYouTube(input);
    }
}

async function fetchVideoInfo(url) {
    UI.showLoader('Fetching video information...');
    try {
        const info = await API.getInfo(url);
        showDownloadReady(info, url);
    } catch (error) {
        UI.toast(error.message, 'error');
    } finally {
        UI.hideLoader();
    }
}

async function searchYouTube(query) {
    UI.showLoader('Searching YouTube...');
    try {
        const results = await API.search(query);
        showSearchResults(results);
    } catch (error) {
        UI.toast(error.message, 'error');
    } finally {
        UI.hideLoader();
    }
}

// ==================== Search Results ====================
function showSearchResults(results) {
    UI.hide('downloadReady');
    UI.hide('progressSection');
    UI.hide('successSection');

    const grid = document.getElementById('resultsGrid');

    if (!results || results.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-search"></i>
                <h3>No results found</h3>
                <p>Try a different search term</p>
            </div>
        `;
    } else {
        grid.innerHTML = results.map(r => `
            <div class="result-card" onclick="selectResult('${encodeURIComponent(r.url)}')">
                <img src="${r.thumbnail}" alt="" class="result-card__thumb" onerror="this.onerror=null;this.src='/static/images/default-album.png';">
                <div class="result-card__info">
                    <div class="result-card__title">${UI.escapeHtml(r.title)}</div>
                    <div class="result-card__meta">${UI.escapeHtml(r.uploader || 'Unknown')} • ${r.duration_str || '0:00'}</div>
                </div>
            </div>
        `).join('');
    }

    UI.show('resultsSection');
}

function selectResult(url) {
    const decodedUrl = decodeURIComponent(url);
    const inputEl = document.getElementById('mainInput');
    if (inputEl) inputEl.value = decodedUrl;
    fetchVideoInfo(decodedUrl);
}

function clearResults() {
    UI.hide('resultsSection');
}

// ==================== Playlist Preview ====================
async function fetchPlaylistInfo(url) {
    UI.showLoader('Loading playlist...');
    try {
        const response = await fetch('/api/playlist/items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error);

        State.currentVideo = { url, is_playlist: true };
        showPlaylistPreview(data);
    } catch (error) {
        UI.toast(error.message, 'error');
    } finally {
        UI.hideLoader();
    }
}

function showPlaylistPreview(data) {
    if (!Array.isArray(data.entries) || data.entries.length === 0) {
        UI.toast('No songs found in this playlist. Please verify the playlist URL.', 'error');
        return;
    }

    State.playlist.items = data.entries;
    State.playlist.selected = new Set(data.entries.map(item => item.id));

    document.getElementById('playlistTitle').textContent = data.title;
    document.getElementById('playlistCount').textContent = `(${data.playlist_count} songs)`;
    document.getElementById('selectedCount').textContent = data.playlist_count;

    const itemsContainer = document.getElementById('playlistItems');
    if (!itemsContainer) return;
    
    itemsContainer.innerHTML = data.entries.map(item => `
        <div class="playlist-item">
            <input type="checkbox" 
                   id="song-${item.id}" 
                   class="playlist-checkbox" 
                   data-id="${item.id}"
                   checked
                   onchange="updateSelectedCount()">
            <img src="${item.thumbnail}" alt="" class="playlist-item__thumb" onerror="this.onerror=null;this.src='/static/images/default-album.png';">
            <div class="playlist-item__info">
                <div class="playlist-item__title">${UI.escapeHtml(item.title)}</div>
                <div class="playlist-item__meta">${UI.escapeHtml(item.uploader || 'Unknown')} • ${item.duration_str || '0:00'}</div>
            </div>
        </div>
    `).join('');

    UI.hide('downloadReady');
    UI.hide('resultsSection');
    UI.show('playlistPreview');
}

function updateSelectedCount() {
    const checkboxes = document.querySelectorAll('.playlist-checkbox');
    State.playlist.selected.clear();

    checkboxes.forEach(cb => {
        if (cb.checked) {
            State.playlist.selected.add(cb.dataset.id);
        }
    });

    document.getElementById('selectedCount').textContent = State.playlist.selected.size;
}

function selectAllSongs() {
    const checkboxes = document.querySelectorAll('.playlist-checkbox');
    checkboxes.forEach(cb => cb.checked = true);
    updateSelectedCount();
}

function deselectAllSongs() {
    const checkboxes = document.querySelectorAll('.playlist-checkbox');
    checkboxes.forEach(cb => cb.checked = false);
    updateSelectedCount();
}

async function downloadSelectedSongs() {
    if (State.playlist.selected.size === 0) {
        UI.toast('Please select at least one song', 'error');
        return;
    }

    UI.toast(`Downloading ${State.playlist.selected.size} songs...`, 'success');
    UI.hide('playlistPreview');

    // Download songs one by one
    let completed = 0;
    const total = State.playlist.selected.size;

    for (const songId of State.playlist.selected) {
        const song = State.playlist.items.find(item => item.id === songId);
        if (!song) continue;

        try {
            State.currentVideo = song;
            const result = await API.startDownload(
                song.url,
                State.format,
                State.quality,
                false
            );

            // Poll for this download
            State.currentJobId = result.job_id;
            await pollUntilComplete(result.job_id);

            completed++;
            UI.toast(`Downloaded ${completed} of ${total}: ${song.title}`, 'success');

        } catch (error) {
            console.error(`Failed to download ${song.title}:`, error);
            UI.toast(`Failed: ${song.title}`, 'error');
        }
    }

    UI.toast(`Playlist download complete! ${completed} of ${total} songs downloaded.`, 'success');
    await loadHistory();
}

async function pollUntilComplete(jobId) {
    return new Promise((resolve, reject) => {
        const pollInterval = setInterval(async () => {
            try {
                const data = await API.getStatus(jobId);

                if (data.status === 'completed') {
                    clearInterval(pollInterval);
                    resolve(data);
                } else if (data.status === 'error') {
                    clearInterval(pollInterval);
                    reject(new Error(data.error || 'Download failed'));
                }
            } catch (error) {
                clearInterval(pollInterval);
                reject(error);
            }
        }, 1000);
    });
}

// ==================== Download Ready ====================
// ==================== Download Ready ====================
function showDownloadReady(info, url) {
    UI.hide('resultsSection');
    UI.hide('progressSection');
    UI.hide('successSection');

    UI.setElement('previewThumb', 'src', info.thumbnail || '');
    UI.setElement('previewTitle', 'textContent', info.title || 'Unknown');
    UI.setElement('previewArtist', 'textContent', info.uploader || 'Unknown Artist');

    // Display different meta for playlist
    if (info.is_playlist) {
        const count = info.track_count || 0;
        UI.setElement('previewDuration', 'innerHTML', `<i class="fas fa-list"></i> ${count} tracks`);

        // Update download button text
        const btn = document.getElementById('downloadNowBtn');
        if (btn) btn.innerHTML = '<i class="fas fa-download"></i> Download Playlist';
    } else {
        UI.setElement('previewDuration', 'innerHTML', `<i class="fas fa-clock"></i> ${info.duration_str || '0:00'}`);
        const btn = document.getElementById('downloadNowBtn');
        if (btn) btn.innerHTML = '<i class="fas fa-download"></i> Download Now';
    }

    const views = info.view_count ? `<i class="fas fa-eye"></i> ${UI.formatNumber(info.view_count)} views` : '';
    UI.setElement('previewViews', 'innerHTML', views);

    UI.toggle('duplicateWarning', false);

    State.currentVideo = { ...info, url };
    UI.show('downloadReady');
}

// ==================== Download ====================
async function startDownload(force = false) {
    if (!State.currentVideo?.url) {
        UI.toast('No video selected', 'error');
        return;
    }

    const btn = document.getElementById('downloadNowBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';

    State.format = document.getElementById('formatSelect').value;

    try {
        const result = await API.startDownload(
            State.currentVideo.url,
            State.format,
            State.quality,
            force
        );

        if (result.skipped_duplicate) {
            UI.hide('downloadReady');
            return;
        }

        if (result.isDuplicate) {
            UI.hide('downloadReady');
            return;
        }

        State.currentJobId = result.job_id;
        showProgress();
        startPolling();

    } catch (error) {
        UI.toast(error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-download"></i> Download Now';
    }
}

function showProgress() {
    UI.hide('downloadReady');

    UI.setElement('progressThumb', 'src', State.currentVideo?.thumbnail || '');
    UI.setElement('progressTitle', 'textContent', State.currentVideo?.title || 'Downloading...');
    UI.setElement('progressFill', 'style', 'width: 0%');
    UI.setElement('progressPercent', 'textContent', '0%');

    UI.show('progressSection');
}

function startPolling() {
    if (State.pollInterval) clearInterval(State.pollInterval);

    State.pollInterval = setInterval(async () => {
        try {
            const data = await API.getStatus(State.currentJobId);

            document.getElementById('progressFill').style.width = `${data.progress || 0}%`;
            UI.setElement('progressPercent', 'textContent', `${Math.round(data.progress || 0)}%`);

            if (data.speed) UI.setElement('progressSpeed', 'textContent', UI.formatSpeed(data.speed));
            if (data.eta) UI.setElement('progressEta', 'textContent', UI.formatTime(data.eta));
            if (data.title) UI.setElement('progressTitle', 'textContent', data.title);

            if (data.status === 'completed') {
                clearInterval(State.pollInterval);
                onDownloadComplete(data);
            } else if (data.status === 'error') {
                clearInterval(State.pollInterval);
                UI.toast(data.error || 'Download failed', 'error');
                UI.hide('progressSection');
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 1000);
}

function onDownloadComplete(data) {
    UI.hide('progressSection');

    State.lastDownloaded = data;
    UI.setElement('successTitle', 'textContent', `"${data.title}" has been downloaded`);

    State.downloads.unshift(data);
    State.library.visibleCount = Math.min(
        State.library.visibleCount + 1,
        State.downloads.length
    );
    updateLibrary();

    // Reload from DB so newly downloaded items get their real record id.
    loadHistory().catch((error) => {
        console.error('Failed to refresh history after download:', error);
    });

    UI.show('successSection');
    UI.toast('Download complete!', 'success');
}

function playDownloaded() {
    if (State.lastDownloaded?.filename) {
        Player.play(
            State.lastDownloaded.filename,
            State.lastDownloaded.title,
            State.lastDownloaded.uploader,
            State.lastDownloaded.thumbnail
        );
    }
}

function hideSuccess() {
    UI.hide('successSection');
    document.getElementById('mainInput').value = '';
    document.getElementById('mainInput')?.focus();
}

// ==================== Queue ====================
async function addToQueue() {
    if (!State.currentVideo?.url) {
        UI.toast('No video selected', 'error');
        return;
    }

    State.format = document.getElementById('formatSelect').value;

    try {
        const result = await API.addToQueue(
            State.currentVideo.url,
            State.currentVideo.title,
            State.currentVideo.thumbnail,
            State.format,
            State.quality,
            {
                video_id: State.currentVideo.id || '',
                artist: State.currentVideo.uploader || '',
                duration: State.currentVideo.duration || 0
            }
        );

        if (result.skipped_duplicate) {
            UI.hide('downloadReady');
            return;
        }

        State.queue.push(result.queue_item);
        updateQueueBadge();
        startQueuePolling();
        UI.toast(`Added to queue (position ${result.position})`, 'success');
        UI.hide('downloadReady');

    } catch (error) {
        UI.toast(error.message, 'error');
    }
}

async function loadQueue() {
    try {
        const data = await API.getQueue();
        applyQueueState(data, { notifyTransitions: false });
    } catch (error) {
        console.error('Failed to load queue:', error);
    }
}

function applyQueueState(data, options = {}) {
    const notifyTransitions = options.notifyTransitions === true;
    const queue = Array.isArray(data?.queue) ? data.queue : [];
    const activeJobs = Array.isArray(data?.active) ? data.active : [];

    State.queue = queue;
    State.queueActive = activeJobs;
    updateQueueBadge();
    updateQueueView();

    let shouldRefreshHistory = false;
    const nextStates = {};
    for (const job of activeJobs) {
        const jobId = String(job?.id || '');
        const status = String(job?.status || 'unknown');
        if (!jobId) continue;

        const previousStatus = State.queueJobStates[jobId];
        nextStates[jobId] = status;

        if (!notifyTransitions || previousStatus === undefined || previousStatus === status) {
            continue;
        }

        if (status === 'completed') {
            shouldRefreshHistory = true;
            UI.toast(`Queue download completed: ${job.title || 'Song'}`, 'success');
        } else if (status === 'error') {
            UI.toast(`Queue download failed: ${job.title || 'Song'}`, 'error');
        }
    }

    State.queueJobStates = { ...State.queueJobStates, ...nextStates };

    if (shouldRefreshHistory) {
        loadHistory().catch((error) => {
            console.error('Failed to refresh history after queue completion:', error);
        });
    }
}

async function pollQueueState() {
    if (State.queuePollBusy) return;
    State.queuePollBusy = true;

    try {
        const data = await API.getQueue();
        applyQueueState(data, { notifyTransitions: true });
    } catch (error) {
        console.error('Queue polling error:', error);
    } finally {
        State.queuePollBusy = false;
    }
}

function startQueuePolling() {
    if (State.queuePollInterval) return;

    pollQueueState().catch((error) => {
        console.error('Initial queue poll failed:', error);
    });

    State.queuePollInterval = setInterval(() => {
        pollQueueState().catch((error) => {
            console.error('Queue polling tick failed:', error);
        });
    }, 1500);
}

function updateQueueBadge() {
    const badge = document.getElementById('queueBadge');
    const mobileBadge = document.getElementById('mobileQueueBadge');

    if (badge) {
        badge.textContent = State.queue.length;
        badge.style.display = State.queue.length > 0 ? 'inline' : 'none';
    }

    if (mobileBadge) {
        mobileBadge.textContent = State.queue.length;
        mobileBadge.style.display = State.queue.length > 0 ? 'inline' : 'none';
    }
}

function updateQueueView() {
    const list = document.getElementById('queueList');
    const count = document.getElementById('queueCount');
    const clearBtn = document.getElementById('clearQueueBtn');

    if (count) count.textContent = `${State.queue.length} item${State.queue.length !== 1 ? 's' : ''} in queue`;
    if (clearBtn) clearBtn.style.display = State.queue.length > 0 ? 'inline-flex' : 'none';

    if (State.queue.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-list"></i>
                <h3>Queue is empty</h3>
                <p>Add songs to download them one by one</p>
            </div>
        `;
        return;
    }

    list.innerHTML = State.queue.map((item, i) => `
        <div class="queue-item">
            <span class="queue-item__number">${i + 1}</span>
            <img src="${item.thumbnail || ''}" alt="" class="queue-item__thumb">
            <div class="queue-item__info">
                <div class="queue-item__title">${UI.escapeHtml(item.title)}</div>
                <div class="queue-item__meta">${item.format} • ${item.status}</div>
            </div>
            <span class="queue-item__status queue-item__status--${item.status}">${item.status}</span>
            <button class="queue-item__remove" onclick="removeFromQueue('${item.id}')">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `).join('');
}

async function removeFromQueue(itemId) {
    try {
        await API.removeFromQueue(itemId);
        State.queue = State.queue.filter(q => q.id !== itemId);
        updateQueueBadge();
        updateQueueView();
    } catch (error) {
        UI.toast('Failed to remove', 'error');
    }
}

async function clearQueue() {
    if (!confirm('Clear the entire queue?')) return;

    try {
        await API.clearQueue();
        State.queue = [];
        updateQueueBadge();
        updateQueueView();
        UI.toast('Queue cleared', 'success');
    } catch (error) {
        UI.toast('Failed to clear', 'error');
    }
}

// ==================== Playlists ====================
function getSelectedPlaylist() {
    return State.playlists.items.find(p => Number(p.id) === Number(State.playlists.selectedId)) || null;
}

async function loadPlaylists(keepSelection = true) {
    try {
        const previousSelected = State.playlists.selectedId;
        const data = await API.getPlaylists();
        State.playlists.items = Array.isArray(data) ? data : [];

        const hasSelected = State.playlists.items.some(
            p => Number(p.id) === Number(State.playlists.selectedId)
        );

        if (!keepSelection || !hasSelected) {
            State.playlists.selectedId = State.playlists.items[0]?.id || null;
        }

        renderPlaylistsList();
        renderAddToPlaylistOptions();
        updatePlaylistPlaybackControls();

        if (State.playlists.selectedId) {
            if (
                Number(previousSelected) !== Number(State.playlists.selectedId)
                || State.playlists.songs.length === 0
            ) {
                await loadSelectedPlaylistSongs();
            } else {
                renderSelectedPlaylistPanel();
            }
        } else {
            State.playlists.songs = [];
            renderSelectedPlaylistPanel();
        }
    } catch (error) {
        console.error('Failed to load playlists:', error);
    }
}

function renderPlaylistsList() {
    const list = document.getElementById('playlistsList');
    if (!list) return;

    if (!State.playlists.items.length) {
        list.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-list-music"></i>
                <h3>No playlists yet</h3>
                <p>Create a playlist to organize your downloaded songs</p>
            </div>
        `;
        return;
    }

    list.innerHTML = State.playlists.items.map(playlist => {
        const isActive = Number(playlist.id) === Number(State.playlists.selectedId);
        return `
            <div class="playlist-list-item ${isActive ? 'playlist-list-item--active' : ''}"
                 onclick="selectPlaylist(${playlist.id})">
                <span class="playlist-list-item__name">${UI.escapeHtml(playlist.name || 'Untitled')}</span>
                <span class="playlist-list-item__meta">${playlist.song_count || 0} song${(playlist.song_count || 0) !== 1 ? 's' : ''}</span>
            </div>
        `;
    }).join('');
}

function renderSelectedPlaylistPanel() {
    const titleEl = document.getElementById('selectedPlaylistName');
    const metaEl = document.getElementById('selectedPlaylistMeta');
    const listEl = document.getElementById('playlistSongsList');
    const deleteBtn = document.getElementById('deletePlaylistBtn');
    if (!titleEl || !metaEl || !listEl || !deleteBtn) return;

    const playlist = getSelectedPlaylist();
    if (!playlist) {
        titleEl.textContent = 'Select a playlist';
        metaEl.textContent = 'Choose a playlist to see songs';
        deleteBtn.style.display = 'none';
        listEl.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-music"></i>
                <h3>No playlist selected</h3>
                <p>Pick a playlist from the left panel</p>
            </div>
        `;
        updatePlaylistPlaybackControls();
        return;
    }

    titleEl.textContent = playlist.name || 'Playlist';
    metaEl.textContent = `${State.playlists.songs.length} song${State.playlists.songs.length !== 1 ? 's' : ''}`;
    deleteBtn.style.display = 'inline-flex';

    if (!State.playlists.songs.length) {
        listEl.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-music"></i>
                <h3>No songs in this playlist</h3>
                <p>Go to My Music and use the + button on a song to add it</p>
            </div>
        `;
        updatePlaylistPlaybackControls();
        return;
    }

    const playingSongId = getCurrentPlaybackSongId();
    listEl.innerHTML = State.playlists.songs.map(song => {
        const songId = Number(song.id);
        const title = song.title || 'Unknown Title';
        const artist = song.artist || song.uploader || 'Unknown Artist';
        const thumbnail = song.thumbnail || '';
        const isPlaying = Number.isFinite(songId) && Number(playingSongId) === songId;

        return `
            <div class="playlist-song-item ${isPlaying ? 'playlist-song-item--playing' : ''}">
                <img src="${thumbnail}" alt="" class="playlist-song-item__thumb" onerror="this.src='/static/images/default-album.png'">
                <div class="playlist-song-item__info">
                    <div class="playlist-song-item__title">${UI.escapeHtml(title)}</div>
                    <div class="playlist-song-item__artist">${UI.escapeHtml(artist)}</div>
                </div>
                <div class="playlist-song-item__actions">
                    <button class="btn btn--icon"
                            title="Play"
                            onclick="playPlaylistSong(${songId})">
                        <i class="fas fa-play"></i>
                    </button>
                    <button class="btn btn--icon"
                            title="Remove from playlist"
                            onclick="removeSongFromSelectedPlaylist(${songId})">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
    updatePlaylistPlaybackControls();
}

async function selectPlaylist(playlistId) {
    const selected = Number(playlistId);
    if (!Number.isFinite(selected) || selected <= 0) return;

    State.playlists.selectedId = selected;
    renderPlaylistsList();
    await loadSelectedPlaylistSongs();
}

async function loadSelectedPlaylistSongs() {
    if (!State.playlists.selectedId) {
        State.playlists.songs = [];
        renderSelectedPlaylistPanel();
        return;
    }

    try {
        const response = await API.getPlaylistSongs(State.playlists.selectedId);
        State.playlists.songs = Array.isArray(response.songs) ? response.songs : [];

        const updatedPlaylist = response.playlist;
        if (updatedPlaylist && updatedPlaylist.id) {
            const idx = State.playlists.items.findIndex(
                p => Number(p.id) === Number(updatedPlaylist.id)
            );
            if (idx !== -1) {
                State.playlists.items[idx] = { ...State.playlists.items[idx], ...updatedPlaylist };
            }
        }

        renderPlaylistsList();
        renderSelectedPlaylistPanel();
    } catch (error) {
        console.error('Failed to load selected playlist songs:', error);
        UI.toast(error.message || 'Failed to load playlist songs', 'error');
    }
}

async function createPlaylist() {
    const input = document.getElementById('newPlaylistName');
    const name = input?.value?.trim() || '';
    if (!name) {
        UI.toast('Enter a playlist name', 'error');
        return;
    }

    try {
        const created = await API.createPlaylist(name);
        if (input) input.value = '';
        await loadPlaylists(true);
        await selectPlaylist(created.id);
        UI.toast('Playlist created', 'success');
    } catch (error) {
        UI.toast(error.message || 'Failed to create playlist', 'error');
    }
}

async function deleteSelectedPlaylist() {
    const playlist = getSelectedPlaylist();
    if (!playlist) return;

    if (!confirm(`Delete playlist "${playlist.name}"?`)) return;

    try {
        await API.deletePlaylist(playlist.id);
        State.playlists.selectedId = null;
        State.playlists.songs = [];
        await loadPlaylists(false);
        UI.toast('Playlist deleted', 'success');
    } catch (error) {
        UI.toast(error.message || 'Failed to delete playlist', 'error');
    }
}

async function removeSongFromSelectedPlaylist(downloadId) {
    const playlist = getSelectedPlaylist();
    if (!playlist) return;

    try {
        await API.removeSongFromPlaylist(playlist.id, downloadId);
        State.playlists.songs = State.playlists.songs.filter(s => Number(s.id) !== Number(downloadId));
        if (State.playback.source === 'playlist' && Number(State.playback.playlistId) === Number(playlist.id)) {
            prunePlaybackQueueAfterDelete(downloadId, '');
        }
        renderSelectedPlaylistPanel();
        await loadPlaylists(true);
        UI.toast('Removed from playlist', 'success');
    } catch (error) {
        UI.toast(error.message || 'Failed to remove song', 'error');
    }
}

async function openAddToPlaylistModal(event, downloadId) {
    event?.preventDefault();
    event?.stopPropagation();

    const id = Number(downloadId);
    if (!Number.isFinite(id) || id <= 0) {
        UI.toast('Invalid song id', 'error');
        return;
    }

    State.playlists.addModalSongId = id;
    const modalNameInput = document.getElementById('modalPlaylistName');
    if (modalNameInput) modalNameInput.value = '';

    UI.show('addToPlaylistModal');
    await loadPlaylists(true);
    renderAddToPlaylistOptions();
}

function closeAddToPlaylistModal() {
    UI.hide('addToPlaylistModal');
    State.playlists.addModalSongId = null;
}

function closeAddToPlaylistModalOnOverlay(event) {
    if (event?.target?.id === 'addToPlaylistModal') {
        closeAddToPlaylistModal();
    }
}

function renderAddToPlaylistOptions() {
    const container = document.getElementById('addToPlaylistOptions');
    if (!container) return;

    if (!State.playlists.items.length) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-list-music"></i>
                <h3>No playlists available</h3>
                <p>Create one above, then add this song</p>
            </div>
        `;
        return;
    }

    container.innerHTML = State.playlists.items.map(playlist => `
        <div class="add-to-playlist-option">
            <span class="add-to-playlist-option__name">${UI.escapeHtml(playlist.name || 'Untitled')}</span>
            <button class="btn btn--secondary btn--small" onclick="addCurrentSongToPlaylist(${playlist.id})">
                <i class="fas fa-plus"></i>
                <span>Add</span>
            </button>
        </div>
    `).join('');
}

async function addCurrentSongToPlaylist(playlistId) {
    const downloadId = Number(State.playlists.addModalSongId);
    if (!Number.isFinite(downloadId) || downloadId <= 0) {
        UI.toast('No song selected', 'error');
        return;
    }

    try {
        await API.addSongToPlaylist(playlistId, downloadId);
        await loadPlaylists(true);
        if (Number(State.playlists.selectedId) === Number(playlistId)) {
            await loadSelectedPlaylistSongs();
        }
        closeAddToPlaylistModal();
        UI.toast('Added to playlist', 'success');
    } catch (error) {
        UI.toast(error.message || 'Failed to add song', 'error');
    }
}

async function createPlaylistFromModal() {
    const input = document.getElementById('modalPlaylistName');
    const name = input?.value?.trim() || '';
    if (!name) {
        UI.toast('Enter a playlist name', 'error');
        return;
    }

    try {
        const created = await API.createPlaylist(name);
        if (input) input.value = '';
        await loadPlaylists(true);
        await addCurrentSongToPlaylist(created.id);
    } catch (error) {
        UI.toast(error.message || 'Failed to create playlist', 'error');
    }
}

function updatePlaylistPlaybackControls() {
    const playAllBtn = document.getElementById('playlistPlayAllBtn');
    const shuffleBtn = document.getElementById('playlistShuffleBtn');
    const loopBtn = document.getElementById('playlistLoopBtn');
    if (!playAllBtn || !shuffleBtn || !loopBtn) return;

    const hasPlaylist = Boolean(getSelectedPlaylist());
    const playableSongs = buildSelectedPlaylistPlaybackQueue().length;
    const canPlay = hasPlaylist && playableSongs > 0;

    playAllBtn.disabled = !canPlay;
    shuffleBtn.disabled = !canPlay;
    loopBtn.disabled = !hasPlaylist;

    shuffleBtn.classList.toggle('active', Player.shuffle === true);
    const shuffleLabel = shuffleBtn.querySelector('span');
    if (shuffleLabel) {
        shuffleLabel.textContent = Player.shuffle ? 'Shuffle On' : 'Shuffle';
    }

    const loopEnabled = Player.repeat === 'all';
    loopBtn.classList.toggle('active', loopEnabled);
    const loopLabel = loopBtn.querySelector('span');
    if (loopLabel) {
        loopLabel.textContent = loopEnabled ? 'Loop: On' : 'Loop: Off';
    }
}

function setShuffleMode(enabled) {
    const shouldEnable = Boolean(enabled);
    if (Boolean(Player.shuffle) !== shouldEnable && typeof Player.toggleShuffle === 'function') {
        Player.toggleShuffle();
    } else {
        updatePlaylistPlaybackControls();
    }
}

function playSelectedPlaylist(shuffleStart = false) {
    const playlist = getSelectedPlaylist();
    if (!playlist) {
        UI.toast('Select a playlist first', 'error');
        return;
    }

    const tracks = buildSelectedPlaylistPlaybackQueue();
    if (!tracks.length) {
        UI.toast('No playable songs in this playlist', 'error');
        return;
    }

    setShuffleMode(shuffleStart);

    let startIndex = 0;
    if (shuffleStart && tracks.length > 1) {
        startIndex = Math.floor(Math.random() * tracks.length);
    }

    if (!setPlaybackQueue('playlist', tracks, startIndex, playlist.id)) {
        UI.toast('No playable songs in this playlist', 'error');
        return;
    }

    playFromCurrentQueue(startIndex);
}

function playPlaylistSong(songId) {
    const targetId = Number(songId);
    if (!Number.isFinite(targetId) || targetId <= 0) {
        UI.toast('Invalid song selected', 'error');
        return;
    }

    const playlist = getSelectedPlaylist();
    const tracks = buildSelectedPlaylistPlaybackQueue();
    const startIndex = tracks.findIndex(track => Number(track.id) === targetId);
    if (startIndex === -1) {
        UI.toast('Song not found in playlist', 'error');
        return;
    }

    setPlaybackQueue('playlist', tracks, startIndex, playlist?.id || null);
    playFromCurrentQueue(startIndex);
}

function togglePlaylistLoop() {
    const playlist = getSelectedPlaylist();
    if (!playlist) {
        UI.toast('Select a playlist first', 'error');
        return;
    }

    Player.repeat = Player.repeat === 'all' ? 'off' : 'all';
    Player.updateRepeatButton?.();
    Player.updateNowPlayingButtons?.();
    Player.saveSettings?.();
    updatePlaylistPlaybackControls();
    UI.toast(Player.repeat === 'all' ? 'Playlist loop enabled' : 'Playlist loop disabled', 'success');
}

// ==================== Library ====================
async function loadHistory() {
    try {
        const data = await API.getHistory();
        State.downloads = Array.isArray(data) ? data : [];
        const supportsLazyLoading = typeof window.IntersectionObserver === 'function';
        State.library.visibleCount = Math.min(
            supportsLazyLoading ? State.library.batchSize : State.downloads.length,
            State.downloads.length
        );
        updateLibrary();
    } catch (error) {
        console.error('Failed to load history:', error);
    }
}

function setupLibraryLazyLoading() {
    const trigger = document.getElementById('libraryLoadTrigger');
    const mainContent = document.getElementById('mainContent');

    if (mainContent && !State.library.scrollListenerAttached) {
        mainContent.addEventListener('scroll', maybeLoadMoreLibraryByScroll, { passive: true });
        State.library.scrollListenerAttached = true;
    }

    if (!trigger || State.library.observer) return;

    // Older browsers may not support IntersectionObserver.
    if (typeof window.IntersectionObserver !== 'function') return;

    State.library.observer = new IntersectionObserver((entries) => {
        if (!isLibraryViewVisible()) return;

        for (const entry of entries) {
            if (entry.isIntersecting) {
                loadMoreLibrarySongs();
                break;
            }
        }
    }, {
        // The app scrolls inside #mainContent, not the window viewport.
        root: mainContent || null,
        rootMargin: '240px 0px',
        threshold: 0
    });

    State.library.observer.observe(trigger);
}

function isLibraryViewVisible() {
    const libraryView = document.getElementById('libraryView');
    return !!libraryView && !libraryView.classList.contains('hidden');
}

function loadMoreLibrarySongs() {
    if (State.library.visibleCount >= State.downloads.length) return;

    State.library.visibleCount = Math.min(
        State.library.visibleCount + State.library.batchSize,
        State.downloads.length
    );
    updateLibrary();
}

function maybeLoadMoreLibraryByScroll() {
    if (!isLibraryViewVisible()) return;
    if (State.library.visibleCount >= State.downloads.length) return;

    const mainContent = document.getElementById('mainContent');
    if (!mainContent) return;

    const remaining = mainContent.scrollHeight - (mainContent.scrollTop + mainContent.clientHeight);
    if (remaining <= 240) {
        loadMoreLibrarySongs();
    }
}

function createLibraryCardMarkup(download) {
    const filename = download.filename || '';
    const title = download.title || 'Unknown Title';
    const artist = download.artist || download.uploader || 'Unknown Artist';
    const thumbnail = download.thumbnail || '';
    const downloadId = Number(download.id);
    const canManage = Number.isFinite(downloadId) && downloadId > 0;

    if (!filename) return '';

    const addButton = canManage ? `
        <button class="library-card__add"
                title="Add to playlist"
                aria-label="Add to playlist"
                onclick="openAddToPlaylistModal(event, ${downloadId})">
            <i class="fas fa-plus"></i>
        </button>
    ` : '';

    const deleteButton = canManage ? `
        <button class="library-card__delete"
                title="Delete song"
                aria-label="Delete song"
                onclick="deleteLibraryTrack(event, ${downloadId})">
            <i class="fas fa-trash"></i>
        </button>
    ` : '';

    return `
        <div class="library-card library-item"
             data-title="${UI.escapeHtml(title)}"
             data-artist="${UI.escapeHtml(artist)}"
             onclick="playTrack('${UI.escapeJs(filename)}', '${UI.escapeJs(title)}', '${UI.escapeJs(artist)}', '${UI.escapeJs(thumbnail)}')">
            ${addButton}
            ${deleteButton}
            <img src="${thumbnail}" alt="" class="library-card__thumb" onerror="this.src='/static/images/default-album.png'">
            <div class="library-card__info">
                <div class="library-card__title">${UI.escapeHtml(title)}</div>
                <div class="library-card__artist">${UI.escapeHtml(artist)}</div>
            </div>
        </div>
    `;
}

async function deleteLibraryTrack(event, downloadId) {
    event?.preventDefault();
    event?.stopPropagation();

    const id = Number(downloadId);
    if (!Number.isFinite(id) || id <= 0) {
        UI.toast('Invalid song id', 'error');
        return;
    }

    const track = State.downloads.find(d => Number(d.id) === id);
    const displayName = track?.title || 'this song';

    if (!confirm(`Delete "${displayName}" from your library and remove the file?`)) {
        return;
    }

    try {
        await API.deleteHistoryItem(id);

        // Stop playback if the deleted file is currently playing.
        const currentTrack = Player.getCurrentTrack?.();
        if (currentTrack?.filename && track?.filename && currentTrack.filename === track.filename) {
            Player.stop?.();
        }

        State.downloads = State.downloads.filter(d => Number(d.id) !== id);
        State.library.visibleCount = Math.min(State.library.visibleCount, State.downloads.length);

        prunePlaybackQueueAfterDelete(id, track?.filename || '');

        updateLibrary();
        await loadPlaylists(true);
        if (isViewActive('playlistsView') && State.playlists.selectedId) {
            await loadSelectedPlaylistSongs();
        }
        updatePlaylistPlaybackControls();
        UI.toast('Song deleted', 'success');
    } catch (error) {
        UI.toast(error.message || 'Failed to delete song', 'error');
    }
}

function updateLibraryLazyStatus() {
    const status = document.getElementById('libraryLoadStatus');
    const trigger = document.getElementById('libraryLoadTrigger');
    if (!status || !trigger) return;

    if (State.downloads.length === 0) {
        status.classList.add('hidden');
        trigger.classList.add('hidden');
        return;
    }

    const hasMore = State.library.visibleCount < State.downloads.length;
    status.classList.remove('hidden');
    status.textContent = hasMore
        ? `Showing ${State.library.visibleCount} of ${State.downloads.length} songs. Scroll down to load more.`
        : `Showing all ${State.downloads.length} songs.`;
    trigger.classList.toggle('hidden', !hasMore);
}

function updateLibrary() {
    const grid = document.getElementById('libraryGrid');
    const count = document.getElementById('libraryCount');
    if (!grid) return;

    if (count) count.textContent = `${State.downloads.length} song${State.downloads.length !== 1 ? 's' : ''}`;

    if (State.downloads.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-music"></i>
                <h3>No songs yet</h3>
                <p>Downloaded songs will appear here</p>
            </div>
        `;
        updateLibraryLazyStatus();
        return;
    }

    const visibleItems = State.downloads.slice(0, State.library.visibleCount);
    grid.innerHTML = visibleItems.map(createLibraryCardMarkup).join('');
    updateLibraryLazyStatus();

    const currentSearch = document.getElementById('librarySearchInput')?.value?.trim();
    if (currentSearch && typeof filterLibrary === 'function') {
        filterLibrary(currentSearch);
    }

    // If the current viewport is already at the bottom area, pull the next batch.
    requestAnimationFrame(maybeLoadMoreLibraryByScroll);
}

// Current playback index in active queue
let currentPlayIndex = -1;

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
        return false;
    }

    State.playback.queue = queue;
    State.playback.source = source || 'library';

    const numericPlaylistId = Number(playlistId);
    State.playback.playlistId = Number.isFinite(numericPlaylistId) && numericPlaylistId > 0
        ? numericPlaylistId
        : null;

    currentPlayIndex = Math.max(0, Math.min(startIndex, queue.length - 1));
    return true;
}

function playFromCurrentQueue(index) {
    if (!Array.isArray(State.playback.queue) || State.playback.queue.length === 0) return;

    const safeIndex = Math.max(0, Math.min(index, State.playback.queue.length - 1));
    const track = State.playback.queue[safeIndex];
    if (!track || !track.filename) return;

    currentPlayIndex = safeIndex;
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
        return;
    }

    if (currentTrack?.filename) {
        const sameTrackIndex = State.playback.queue.findIndex(
            track => track.filename === currentTrack.filename
        );
        if (sameTrackIndex !== -1) {
            currentPlayIndex = sameTrackIndex;
            return;
        }
    }

    currentPlayIndex = Math.min(currentPlayIndex, State.playback.queue.length - 1);
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
        // Random track (not the same as current)
        do {
            nextIndex = Math.floor(Math.random() * queue.length);
        } while (nextIndex === currentPlayIndex && queue.length > 1);
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

// ==================== Views ====================
function showView(viewName) {
    // View name mapping for nav matching
    const viewNavMap = {
        'download': 'download',
        'library': 'library',
        'playlists': 'playlists',
        'queue': 'queue',
        'playlist-downloads': 'playlist-downloads'
    };
    const navName = viewNavMap[viewName] || viewName;
    
    // Update nav using data attribute or text matching
    document.querySelectorAll('.nav-link').forEach(link => {
        const linkView = link.dataset.view || link.textContent.toLowerCase().trim();
        link.classList.toggle('active', linkView === navName);
    });

    // Update views
    document.querySelectorAll('.view').forEach(view => view.classList.add('hidden'));

    if (viewName === 'download') {
        document.getElementById('downloadView')?.classList.remove('hidden');
    } else if (viewName === 'library') {
        document.getElementById('libraryView')?.classList.remove('hidden');
        updateLibrary();
        requestAnimationFrame(maybeLoadMoreLibraryByScroll);
    } else if (viewName === 'playlists') {
        document.getElementById('playlistsView')?.classList.remove('hidden');
        loadPlaylists(true).catch((error) => {
            console.error('Failed to refresh playlists view:', error);
        });
    } else if (viewName === 'queue') {
        document.getElementById('queueView')?.classList.remove('hidden');
        updateQueueView();
    } else if (viewName === 'playlist-downloads') {
        document.getElementById('playlistDownloadsView')?.classList.remove('hidden');
    }
    
    // Update mobile nav if function exists
    if (typeof updateMobileNav === 'function') {
        updateMobileNav(viewName);
    }
}

// ==================== Settings ====================
async function loadSettings() {
    try {
        const settings = await API.getSettings();

        if (settings.default_format) {
            State.format = settings.default_format;
            const formatSelect = document.getElementById('formatSelect');
            if (formatSelect) formatSelect.value = settings.default_format;
            const settingsFormat = document.getElementById('settingsFormat');
            if (settingsFormat) settingsFormat.value = settings.default_format;
        }

        if (settings.default_quality) {
            State.quality = settings.default_quality;
            const settingsQuality = document.getElementById('settingsQuality');
            if (settingsQuality) settingsQuality.value = settings.default_quality;
        }

        const dupCheck = document.getElementById('settingsDuplicates');
        if (dupCheck) dupCheck.checked = settings.check_duplicates !== false;

    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

async function saveSettings(e) {
    e?.preventDefault();

    try {
        await API.saveSettings({
            default_format: document.getElementById('settingsFormat').value,
            default_quality: document.getElementById('settingsQuality').value,
            check_duplicates: true,
            skip_duplicates: true
        });

        closeSettings();
        UI.toast('Settings saved', 'success');
    } catch (error) {
        UI.toast('Failed to save settings', 'error');
    }
}

function openSettings() {
    document.getElementById('settingsModal')?.classList.remove('hidden');
}

function closeSettings() {
    document.getElementById('settingsModal')?.classList.add('hidden');
}

// ==================== Folder ====================
async function openFolder() {
    try {
        await API.openFolder();
        UI.toast('Opening downloads folder...', 'success');
    } catch (error) {
        UI.toast('Failed to open folder', 'error');
    }
}

// ==================== Player Wrappers ====================
function togglePlay() {
    Player.toggle();
}

function seekAudio(event) {
    Player.seek(event);
}

// ==================== Playlist Download Progress Tracker ====================
async function downloadSelectedSongsNew() {
    if (State.playlist.selected.size === 0) {
        UI.toast('Please select at least one song', 'error');
        return;
    }

    const selectedSongs = State.playlist.items.filter(
        item => State.playlist.selected.has(item.id)
    );

    try {
        const response = await fetch('/api/playlist-download/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ songs: selectedSongs })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error);

        State.playlistSession = data.session_id;
        State.playlistDownload.sessionId = data.session_id;
        State.playlistDownload.inProgress = true;
        localStorage.setItem('playlist_download_session', data.session_id);

        // Switch to playlist downloads view
        showView('playlist-downloads');

        // Start polling for updates
        startPlaylistPolling();

        UI.toast('Playlist download started!', 'success');
        UI.hide('playlistPreview');

    } catch (error) {
        UI.toast(error.message, 'error');
    }
}

function isViewActive(viewId) {
    const el = document.getElementById(viewId);
    return el && !el.classList.contains('hidden');
}

function startPlaylistPolling() {
    if (State.playlistPollInterval) {
        clearInterval(State.playlistPollInterval);
    }

    State.playlistPollInterval = setInterval(async () => {
        if (!State.playlistSession) return;

        try {
            const response = await fetch(
                `/api/playlist-download/status/${State.playlistSession}`
            );

            if (!response.ok) {
                clearInterval(State.playlistPollInterval);
                return;
            }

            const session = await response.json();
            State.playlistDownload.lastStatus = session;
            State.playlistDownload.inProgress = (session.completed + session.failed) < session.total;

            // Only update view if it's active
            if (isViewActive('playlistDownloadsView')) {
                updatePlaylistDownloadView(session);
            }

            // Check if completed
            if (session.completed + session.failed >= session.total) {
                clearInterval(State.playlistPollInterval);
                localStorage.removeItem('playlist_download_session');
                State.playlistDownload.inProgress = false;
                UI.toast(
                    `Playlist complete! ${session.completed} of ${session.total} downloaded.`,
                    'success'
                );
                await loadHistory();
            }

        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 1000);
}

function updatePlaylistDownloadView(session) {
    const noActiveEl = document.getElementById('noActiveDownload');
    const activeEl = document.getElementById('activePlaylistDownload');
    if (!noActiveEl || !activeEl) return;

    UI.hide('noActiveDownload');
    UI.show('activePlaylistDownload');

    const completed = session.completed;
    const total = session.total;
    const percentage = Math.round((completed / total) * 100);

    document.getElementById('overallStatus').textContent =
        'Downloading playlist...';
    document.getElementById('overallCount').textContent =
        `${completed} of ${total} completed`;
    document.getElementById('overallPercent').textContent =
        `${percentage}%`;
    document.getElementById('overallProgressBar').style.width =
        `${percentage}%`;

    const listContainer = document.getElementById('playlistDownloadList');
    listContainer.innerHTML = session.songs.map(song => `
        <div class="playlist-download-item playlist-download-item--${song.status}">
            <div class="status-icon">
                ${getStatusIcon(song.status)}
            </div>
            <img src="${song.thumbnail}" alt="" class="item-thumb">
            <div class="item-info">
                <div class="item-title">${UI.escapeHtml(song.title)}</div>
                <div class="item-meta">${UI.escapeHtml(song.uploader)} • ${song.duration_str}</div>
                ${song.status === 'downloading' ? `
                    <div class="progress-bar progress-bar--small">
                        <div class="progress-bar__fill" style="width: ${song.progress}%"></div>
                    </div>
                    <div class="item-stats">
                        <span>${song.progress}%</span>
                        ${song.speed ? `<span>${UI.formatSpeed(song.speed)}</span>` : ''}
                        ${song.eta ? `<span>${UI.formatTime(song.eta)}</span>` : ''}
                    </div>
                ` : `
                    <div class="item-status">${getStatusText(song.status, song.error)}</div>
                `}
            </div>
        </div>
    `).join('');
}

function getStatusIcon(status) {
    const icons = {
        'queued': '<i class="fas fa-clock"></i>',
        'downloading': '<i class="fas fa-spinner fa-spin"></i>',
        'completed': '<i class="fas fa-check-circle"></i>',
        'skipped': '<i class="fas fa-forward"></i>',
        'failed': '<i class="fas fa-exclamation-circle"></i>'
    };
    return icons[status] || '';
}

function getStatusText(status, error) {
    if (status === 'completed') return 'Completed';
    if (status === 'skipped') return error ? `Skipped: ${error}` : 'Skipped (already in library)';
    if (status === 'queued') return 'Waiting...';
    if (status === 'failed') return `Failed: ${error || 'Unknown error'}`;
    return status;
}

// Override old downloadSelectedSongs  
// Override old downloadSelectedSongs  
downloadSelectedSongs = downloadSelectedSongsNew;
