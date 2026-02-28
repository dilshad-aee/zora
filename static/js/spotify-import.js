/**
 * Spotify Import — Standalone import view with history and job detail.
 */

let _importPollTimer = null;
let _currentImportJobId = null;
let _importPollErrors = 0;

/**
 * Called by showView('import') — loads history and resumes polling for active jobs.
 */
async function loadImportView() {
    await loadImportHistory();

    // Resume polling if there's an active job
    try {
        const data = await API.spotify.getJobs();
        const activeJob = (data.jobs || []).find(j => j.status === 'processing' || j.status === 'pending');
        if (activeJob && !_importPollTimer) {
            _currentImportJobId = activeJob.id;

            // Show the active progress panel
            const active = document.getElementById('importActive');
            active.classList.remove('hidden');
            const label = active.querySelector('.import-active__label');
            label.innerHTML = '<i class="fas fa-compact-disc fa-spin"></i><span>Importing...</span>';

            document.getElementById('importActivePlaylistName').textContent = activeJob.playlist_name || 'Loading...';
            const pct = activeJob.total_tracks > 0
                ? Math.round(((activeJob.downloaded + activeJob.skipped + activeJob.failed) / activeJob.total_tracks) * 100)
                : 0;
            document.getElementById('importActiveProgressBar').style.width = `${pct}%`;
            document.getElementById('importActivePct').textContent = `${pct}%`;
            document.getElementById('importActiveDownloaded').textContent = activeJob.downloaded || 0;
            document.getElementById('importActiveSkipped').textContent = activeJob.skipped || 0;
            document.getElementById('importActiveFailed').textContent = activeJob.failed || 0;

            startImportPoll(activeJob.id);
        }
    } catch (err) {
        console.warn('Could not check for active imports:', err);
    }
}

/**
 * Start a new Spotify playlist import.
 */
async function startImport() {
    const input = document.getElementById('importUrlInput');
    const url = (input?.value || '').trim();

    if (!url || !url.includes('spotify.com/playlist/')) {
        showImportError('Please enter a valid Spotify playlist URL (e.g. https://open.spotify.com/playlist/...)');
        return;
    }

    const btn = document.getElementById('importStartBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';
    hideImportError();

    try {
        const job = await API.spotify.startImport(url);
        _currentImportJobId = job.id;

        // Show active progress
        const active = document.getElementById('importActive');
        active.classList.remove('hidden');

        document.getElementById('importActivePlaylistName').textContent = job.playlist_name || 'Fetching playlist...';
        document.getElementById('importActiveProgressBar').style.width = '0%';
        document.getElementById('importActivePct').textContent = '0%';
        document.getElementById('importActiveCurrentTrack').textContent = 'Fetching playlist from Spotify...';
        document.getElementById('importActiveDownloaded').textContent = '0';
        document.getElementById('importActiveSkipped').textContent = '0';
        document.getElementById('importActiveFailed').textContent = '0';

        startImportPoll(job.id);
        input.value = '';
    } catch (err) {
        showImportError(err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-arrow-right"></i><span>Import</span>';
    }
}

/**
 * Polling for active import job.
 */
function startImportPoll(jobId) {
    stopImportPoll();
    _importPollErrors = 0;
    pollImportStatus(jobId); // immediate first poll
    _importPollTimer = setInterval(() => pollImportStatus(jobId), 3000);
}

function stopImportPoll() {
    if (_importPollTimer) {
        clearInterval(_importPollTimer);
        _importPollTimer = null;
    }
}

async function pollImportStatus(jobId) {
    try {
        const data = await API.spotify.getStatus(jobId);
        _importPollErrors = 0; // reset on success
        updateImportProgress(data);

        if (data.status === 'completed' || data.status === 'failed') {
            stopImportPoll();
            onImportFinished(data);
        }
    } catch (err) {
        _importPollErrors++;
        console.error('Import poll error:', err);
        if (_importPollErrors >= 10) {
            stopImportPoll();
            UI.toast('Lost connection to import job. Refresh to check status.', 'error');
        }
    }
}

function updateImportProgress(data) {
    const total = data.total_tracks || 0;
    const processed = (data.downloaded || 0) + (data.skipped || 0) + (data.failed || 0);

    if (data.playlist_name && data.playlist_name !== 'Loading...') {
        document.getElementById('importActivePlaylistName').textContent = data.playlist_name;
    }

    if (total > 0) {
        const pct = Math.round((processed / total) * 100);
        document.getElementById('importActiveProgressBar').style.width = `${pct}%`;
        document.getElementById('importActivePct').textContent = `${pct}%`;
    }

    document.getElementById('importActiveCurrentTrack').textContent = data.current_track || 'Processing...';
    document.getElementById('importActiveDownloaded').textContent = data.downloaded || 0;
    document.getElementById('importActiveSkipped').textContent = data.skipped || 0;
    document.getElementById('importActiveFailed').textContent = data.failed || 0;
}

function onImportFinished(data) {
    // Update header to show completed
    const active = document.getElementById('importActive');
    const label = active.querySelector('.import-active__label');
    if (data.status === 'completed') {
        label.innerHTML = '<i class="fas fa-check-circle"></i><span>Import Complete</span>';
    } else {
        label.innerHTML = '<i class="fas fa-times-circle"></i><span>Import Failed</span>';
    }

    UI.toast(
        data.status === 'completed'
            ? `Import complete! ${data.downloaded || 0} tracks downloaded.`
            : 'Import failed. Check details below.',
        data.status === 'completed' ? 'success' : 'error'
    );

    // Refresh history
    loadImportHistory();
}

/**
 * Load import history list.
 */
async function loadImportHistory() {
    try {
        const data = await API.spotify.getJobs();
        renderImportHistory(data.jobs || []);
    } catch (err) {
        console.error('Failed to load import history:', err);
    }
}

function renderImportHistory(jobs) {
    const container = document.getElementById('importHistoryList');

    if (!jobs.length) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fab fa-spotify"></i>
                <h3>No imports yet</h3>
                <p>Paste a Spotify playlist URL above to get started</p>
            </div>`;
        return;
    }

    container.innerHTML = jobs.map(job => {
        const isActive = job.status === 'processing' || job.status === 'pending';
        const statusClass = job.status === 'completed' ? 'success'
            : job.status === 'failed' ? 'danger'
            : isActive ? 'active'
            : 'pending';
        const statusIcon = job.status === 'completed' ? 'fa-check-circle'
            : job.status === 'failed' ? 'fa-times-circle'
            : isActive ? 'fa-spinner fa-spin'
            : 'fa-clock';
        const statusLabel = job.status === 'completed' ? 'Completed'
            : job.status === 'failed' ? 'Failed'
            : isActive ? 'Importing...'
            : 'Pending';

        const date = job.created_at ? new Date(job.created_at).toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric'
        }) : '';

        const matchRate = job.match_rate != null ? `${job.match_rate}% match` : '';
        const total = job.total_tracks || 0;

        return `
            <div class="import-history-card" data-job-id="${job.id}">
                <div class="import-history-card__main">
                    <div class="import-history-card__info">
                        <h4 class="import-history-card__title">${UI.escapeHtml(job.playlist_name || 'Untitled')}</h4>
                        <div class="import-history-card__meta">
                            <span>${total} tracks</span>
                            ${matchRate ? `<span class="import-history-card__match">${matchRate}</span>` : ''}
                            <span>${date}</span>
                        </div>
                    </div>
                    <span class="import-status-badge import-status-badge--${statusClass}">
                        <i class="fas ${statusIcon}"></i> ${statusLabel}
                    </span>
                </div>
                <div class="import-history-card__actions">
                    <button class="btn btn--ghost btn--small" onclick="showJobDetail('${job.id}')">
                        <i class="fas fa-list"></i> View Tracks
                    </button>
                    ${job.status === 'completed' ? `
                        <button class="btn btn--ghost btn--small" onclick="saveJobAsPlaylist('${job.id}', '${UI.escapeHtml(job.playlist_name || 'Spotify Import')}')">
                            <i class="fas fa-list-ul"></i> Save as Playlist
                        </button>
                    ` : ''}
                </div>
            </div>`;
    }).join('');
}

/**
 * Show track-level detail for a job.
 */
async function showJobDetail(jobId) {
    const detail = document.getElementById('importJobDetail');
    const history = document.getElementById('importHistory');

    detail.classList.remove('hidden');
    history.classList.add('hidden');

    document.getElementById('importJobDetailTitle').textContent = 'Loading...';
    document.getElementById('importJobDetailSummary').innerHTML = '';
    document.getElementById('importJobDetailTracks').innerHTML = '<div class="empty-state"><i class="fas fa-spinner fa-spin"></i><p>Loading tracks...</p></div>';

    try {
        const data = await API.spotify.getStatus(jobId);

        document.getElementById('importJobDetailTitle').textContent = data.playlist_name || 'Import Details';

        // Summary
        const total = data.total_tracks || 0;
        const matchRate = data.match_rate != null ? data.match_rate : 0;
        document.getElementById('importJobDetailSummary').innerHTML = `
            <div class="import-job-summary">
                <div class="import-stat import-stat--success">
                    <span class="import-stat__value">${data.downloaded || 0}</span>
                    <span class="import-stat__label">Downloaded</span>
                </div>
                <div class="import-stat import-stat--warning">
                    <span class="import-stat__value">${data.skipped || 0}</span>
                    <span class="import-stat__label">Skipped</span>
                </div>
                <div class="import-stat import-stat--danger">
                    <span class="import-stat__value">${data.failed || 0}</span>
                    <span class="import-stat__label">Failed</span>
                </div>
                <div class="import-stat">
                    <span class="import-stat__value">${matchRate}%</span>
                    <span class="import-stat__label">Match Rate</span>
                </div>
            </div>`;

        // Track list
        const tracks = data.tracks || [];
        if (!tracks.length) {
            document.getElementById('importJobDetailTracks').innerHTML = '<p class="text-muted" style="padding:16px">No track details available</p>';
            return;
        }

        document.getElementById('importJobDetailTracks').innerHTML = tracks.map(t => {
            const icon = t.status === 'downloaded' ? 'fa-check-circle text-success'
                : t.status === 'skipped' ? 'fa-minus-circle text-warning'
                : t.status === 'failed' ? 'fa-times-circle text-danger'
                : 'fa-circle text-muted';

            return `
                <div class="import-track-row">
                    <i class="fas ${icon} import-track-row__icon"></i>
                    <div class="import-track-row__info">
                        <span class="import-track-row__title">${UI.escapeHtml(t.title || 'Unknown')}</span>
                        <span class="import-track-row__artist">${UI.escapeHtml(t.artist || '')}</span>
                    </div>
                    ${t.score ? `<span class="import-track-row__score">${t.score}</span>` : ''}
                    ${t.reason ? `<span class="import-track-row__reason">${UI.escapeHtml(t.reason)}</span>` : ''}
                </div>`;
        }).join('');

    } catch (err) {
        document.getElementById('importJobDetailTracks').innerHTML = `<p class="text-muted" style="padding:16px">Failed to load: ${UI.escapeHtml(err.message)}</p>`;
    }
}

function closeJobDetail() {
    document.getElementById('importJobDetail').classList.add('hidden');
    document.getElementById('importHistory').classList.remove('hidden');
}

/**
 * Save a completed job's tracks as a Zora playlist.
 */
async function saveJobAsPlaylist(jobId, defaultName) {
    const name = prompt('Playlist name:', defaultName || 'Spotify Import');
    if (!name) return;

    try {
        const result = await API.spotify.saveAsPlaylist(jobId, name);
        UI.toast(`Playlist "${name}" created with ${result.tracks_added} tracks!`, 'success');
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

async function saveActiveJobAsPlaylist() {
    if (!_currentImportJobId) return;

    const name = document.getElementById('importActivePlaylistName')?.textContent || 'Spotify Import';
    await saveJobAsPlaylist(_currentImportJobId, name);
}

/**
 * Error display helpers.
 */
function showImportError(msg) {
    const el = document.getElementById('importError');
    el.textContent = msg;
    el.classList.remove('hidden');
}

function hideImportError() {
    document.getElementById('importError')?.classList.add('hidden');
}
