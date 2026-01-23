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
    playlist: {
        items: [],
        selected: new Set()
    },
    playlistSession: null,
    playlistPollInterval: null
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

    // Load data
    await loadSettings();
    await loadHistory();
    await loadQueue();
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

    input?.focus();
}

// ==================== Main Actions ====================
async function handleMainAction() {
    const input = document.getElementById('mainInput').value.trim();
    if (!input) {
        UI.toast('Please enter a URL or search term', 'error');
        return;
    }

    const isUrl = input.includes('youtube.com') || input.includes('youtu.be') || input.includes('music.youtube');
    const isPlaylistUrl = input.includes('list=');

    if (State.mode === 'playlist' || (isUrl && isPlaylistUrl)) {
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
            <div class="result-card" onclick="selectResult('${r.url}')">
                <img src="${r.thumbnail}" alt="" class="result-card__thumb">
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
    document.getElementById('mainInput').value = url;
    fetchVideoInfo(url);
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
    State.playlist.items = data.entries;
    State.playlist.selected = new Set(data.entries.map(item => item.id));

    document.getElementById('playlistTitle').textContent = data.title;
    document.getElementById('playlistCount').textContent = `(${data.playlist_count} songs)`;
    document.getElementById('selectedCount').textContent = data.playlist_count;

    const itemsContainer = document.getElementById('playlistItems');
    itemsContainer.innerHTML = data.entries.map(item => `
        <div class="playlist-item">
            <input type="checkbox" 
                   id="song-${item.id}" 
                   class="playlist-checkbox" 
                   data-id="${item.id}"
                   checked
                   onchange="updateSelectedCount()">
            <img src="${item.thumbnail}" alt="" class="playlist-item__thumb">
            <div class="playlist-item__info">
                <div class="playlist-item__title">${UI.escapeHtml(item.title)}</div>
                <div class="playlist-item__meta">${UI.escapeHtml(item.uploader)} • ${item.duration_str}</div>
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

    UI.toggle('duplicateWarning', info.is_duplicate);

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

        if (result.isDuplicate) {
            if (confirm(`"${result.title}" already exists.\n\nDownload anyway?`)) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-download"></i> Download Now';
                return startDownload(true);
            }
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-download"></i> Download Now';
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
    updateLibrary();

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
            State.quality
        );

        State.queue.push(result.queue_item);
        updateQueueBadge();
        UI.toast(`Added to queue (position ${result.position})`, 'success');
        UI.hide('downloadReady');

    } catch (error) {
        UI.toast(error.message, 'error');
    }
}

async function loadQueue() {
    try {
        const data = await API.getQueue();
        State.queue = data.queue || [];
        updateQueueBadge();
        updateQueueView();
    } catch (error) {
        console.error('Failed to load queue:', error);
    }
}

function updateQueueBadge() {
    const badge = document.getElementById('queueBadge');
    if (badge) {
        badge.textContent = State.queue.length;
        badge.style.display = State.queue.length > 0 ? 'inline' : 'none';
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

// ==================== Library ====================
async function loadHistory() {
    try {
        const data = await API.getHistory();
        State.downloads = data || [];
        updateLibrary();
    } catch (error) {
        console.error('Failed to load history:', error);
    }
}

function updateLibrary() {
    const grid = document.getElementById('libraryGrid');
    const count = document.getElementById('libraryCount');

    if (count) count.textContent = `${State.downloads.length} song${State.downloads.length !== 1 ? 's' : ''}`;

    if (State.downloads.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-music"></i>
                <h3>No songs yet</h3>
                <p>Downloaded songs will appear here</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = State.downloads.slice(0, 20).map(d => `
        <div class="library-card" onclick="playTrack('${UI.escapeJs(d.filename)}', '${UI.escapeJs(d.title)}', '${UI.escapeJs(d.uploader)}', '${d.thumbnail || ''}')">
            <img src="${d.thumbnail || ''}" alt="" class="library-card__thumb">
            <div class="library-card__info">
                <div class="library-card__title">${UI.escapeHtml(d.title || 'Unknown')}</div>
                <div class="library-card__artist">${UI.escapeHtml(d.uploader || 'Unknown')}</div>
            </div>
        </div>
    `).join('');
}

function playTrack(filename, title, artist, thumbnail) {
    Player.play(filename, title, artist, thumbnail);
}

// ==================== Views ====================
function showView(viewName) {
    // Update nav
    document.querySelectorAll('.nav-link').forEach(link => {
        const text = link.textContent.toLowerCase().trim();
        link.classList.toggle('active', text.includes(viewName));
    });

    // Update views
    document.querySelectorAll('.view').forEach(view => view.classList.add('hidden'));

    if (viewName === 'download') {
        document.getElementById('downloadView')?.classList.remove('hidden');
    } else if (viewName === 'library') {
        document.getElementById('libraryView')?.classList.remove('hidden');
        updateLibrary();
    } else if (viewName === 'queue') {
        document.getElementById('queueView')?.classList.remove('hidden');
        updateQueueView();
    } else if (viewName === 'playlist-downloads') {
        document.getElementById('playlistDownloadsView')?.classList.remove('hidden');
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
            check_duplicates: document.getElementById('settingsDuplicates').checked
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
            updatePlaylistDownloadView(session);

            // Check if completed
            if (session.completed + session.failed >= session.total) {
                clearInterval(State.playlistPollInterval);
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
        'failed': '<i class="fas fa-exclamation-circle"></i>'
    };
    return icons[status] || '';
}

function getStatusText(status, error) {
    if (status === 'completed') return 'Completed';
    if (status === 'queued') return 'Waiting...';
    if (status === 'failed') return `Failed: ${error || 'Unknown error'}`;
    return status;
}

// Override old downloadSelectedSongs  
// Override old downloadSelectedSongs  
downloadSelectedSongs = downloadSelectedSongsNew;
