/**
 * Zora - Downloads Module
 * Download flow, search, tab switching, and progress tracking
 * 
 * Dependencies: api.js, ui.js, player.js, app.js (State, loadHistory, updateLibrary)
 */

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

function setPlaylistAutoCreateState(enabled) {
    const checked = Boolean(enabled);
    State.playlist.autoCreate = checked;

    const previewOption = document.getElementById('autoCreatePlaylistCheckbox');
    if (previewOption && previewOption.checked !== checked) {
        previewOption.checked = checked;
    }
}

function getPlaylistAutoCreateState() {
    const previewOption = document.getElementById('autoCreatePlaylistCheckbox');

    if (previewOption) return Boolean(previewOption.checked);
    return Boolean(State.playlist.autoCreate);
}

// ==================== Main Action ====================
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

// ==================== Playlist ====================
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

    State.playlist.items = data.entries.map((item, index) => ({
        ...item,
        entry_key: `${item.id || 'track'}::${index}`
    }));
    State.playlist.selected = new Set(State.playlist.items.map(item => item.entry_key));
    State.playlist.title = data.title || 'Playlist';

    document.getElementById('playlistTitle').textContent = data.title;
    document.getElementById('playlistCount').textContent = `(${data.playlist_count} songs)`;
    document.getElementById('selectedCount').textContent = data.playlist_count;

    const createPlaylistCheckbox = document.getElementById('autoCreatePlaylistCheckbox');
    if (createPlaylistCheckbox) {
        setPlaylistAutoCreateState(Boolean(State.playlist.autoCreate));
    }

    const itemsContainer = document.getElementById('playlistItems');
    if (!itemsContainer) return;
    
    itemsContainer.innerHTML = State.playlist.items.map((item, index) => `
        <div class="playlist-item">
            <input type="checkbox" 
                   id="song-${index}" 
                   class="playlist-checkbox" 
                   data-entry-key="${item.entry_key}"
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
            State.playlist.selected.add(cb.dataset.entryKey);
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

    for (const songKey of State.playlist.selected) {
        const song = State.playlist.items.find(item => item.entry_key === songKey);
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
function showDownloadReady(info, url) {
    UI.hide('resultsSection');
    UI.hide('progressSection');
    UI.hide('successSection');

    UI.setElement('previewThumb', 'src', info.thumbnail || '/static/images/default-album.png');
    UI.setElement('previewTitle', 'textContent', info.title || 'Unknown');
    UI.setElement('previewArtist', 'textContent', info.uploader || 'Unknown Artist');

    // Display different meta for playlist
    if (info.is_playlist) {
        const count = info.track_count || 0;
        UI.setElement('previewTypeBadge', 'textContent', 'Playlist');
        UI.setElement('previewDuration', 'innerHTML', `<i class="fas fa-list"></i> ${count} tracks`);

        // Update download button text
        const btn = document.getElementById('downloadNowBtn');
        if (btn) btn.innerHTML = '<i class="fas fa-download"></i> Download Playlist';
    } else {
        UI.setElement('previewTypeBadge', 'textContent', 'Single Track');
        UI.setElement('previewDuration', 'innerHTML', `<i class="fas fa-clock"></i> ${info.duration_str || '0:00'}`);
        const btn = document.getElementById('downloadNowBtn');
        if (btn) btn.innerHTML = '<i class="fas fa-download"></i> Download Now';
    }

    const views = info.view_count
        ? `<i class="fas fa-eye"></i> ${UI.formatNumber(info.view_count)} views`
        : '<i class="fas fa-chart-line"></i> Views unavailable';
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
        btn.innerHTML = State.currentVideo?.is_playlist
            ? '<i class="fas fa-download"></i> Download Playlist'
            : '<i class="fas fa-download"></i> Download Now';
    }
}

function showProgress() {
    UI.hide('downloadReady');

    UI.setElement('progressThumb', 'src', State.currentVideo?.thumbnail || '/static/images/default-album.png');
    UI.setElement('progressTitle', 'textContent', State.currentVideo?.title || 'Downloading...');
    UI.setElement('progressFill', 'style', 'width: 0%');
    UI.setElement('progressPercent', 'textContent', '0%');

    UI.show('progressSection');
}

function startPolling() {
    if (State.pollInterval) clearInterval(State.pollInterval);
    let consecutivePollErrors = 0;

    State.pollInterval = setInterval(async () => {
        try {
            const data = await API.getStatus(State.currentJobId);
            consecutivePollErrors = 0;

            document.getElementById('progressFill').style.width = `${data.progress || 0}%`;
            UI.setElement('progressPercent', 'textContent', `${Math.round(data.progress || 0)}%`);

            if (data.speed) UI.setElement('progressSpeed', 'textContent', UI.formatSpeed(data.speed));
            if (data.eta) UI.setElement('progressEta', 'textContent', UI.formatTime(data.eta));
            if (data.title) UI.setElement('progressTitle', 'textContent', data.title);

            if (data.status === 'completed') {
                clearInterval(State.pollInterval);
                State.pollInterval = null;
                onDownloadComplete(data);
            } else if (data.status === 'error') {
                clearInterval(State.pollInterval);
                State.pollInterval = null;
                UI.toast(data.error || 'Download failed', 'error');
                UI.hide('progressSection');
            }
        } catch (error) {
            console.error('Polling error:', error);
            consecutivePollErrors += 1;

            if (consecutivePollErrors >= 3) {
                clearInterval(State.pollInterval);
                State.pollInterval = null;
                UI.hide('progressSection');
                UI.toast(error.message || 'Download status unavailable', 'error');
            }
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
