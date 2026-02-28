/**
 * Zora - Admin & Settings Module
 * Admin panel, audit logs, settings, playlist download tracking
 * 
 * Dependencies: api.js, ui.js, player.js, app.js (State, showView)
 *               playlists.js (getPlaylistAutoCreateState, loadPlaylists)
 *               library.js (loadHistory)
 */

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

        const settingsDownloadDir = document.getElementById('settingsDownloadDir');
        if (settingsDownloadDir) {
            settingsDownloadDir.value = settings.download_dir || '';
        }

        const settingsPlaylistPreviewLimit = document.getElementById('settingsPlaylistPreviewLimit');
        if (settingsPlaylistPreviewLimit) {
            const raw = Number(settings.playlist_preview_limit);
            const safe = Number.isFinite(raw) ? Math.min(Math.max(raw, 20), 500) : 120;
            settingsPlaylistPreviewLimit.value = safe;
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
            download_dir: document.getElementById('settingsDownloadDir')?.value?.trim() || '',
            playlist_preview_limit: Number(document.getElementById('settingsPlaylistPreviewLimit')?.value || 120),
            check_duplicates: true,
            skip_duplicates: true
        });

        await loadHistory();
        if (State.playlists.selectedId) {
            await loadSelectedPlaylistSongs();
        }

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
        item => State.playlist.selected.has(item.entry_key)
    );
    const autoCreatePlaylist = getPlaylistAutoCreateState();
    const playlistName = autoCreatePlaylist
        ? (State.playlist.title || 'Downloaded Playlist')
        : '';

    try {
        const response = await API._fetch('/api/playlist-download/start',
            API._jsonOptions('POST', {
                songs: selectedSongs,
                create_playlist: autoCreatePlaylist,
                playlist_name: playlistName
            })
        );

        const data = await response.json();
        if (!response.ok) throw new Error(data.error);

        State.playlistSession = data.session_id;
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
            const response = await API._fetch(
                `/api/playlist-download/status/${State.playlistSession}`
            );

            if (!response.ok) {
                clearInterval(State.playlistPollInterval);
                return;
            }

            const session = await response.json();

            // Only update view if it's active
            if (isViewActive('playlistDownloadsView')) {
                updatePlaylistDownloadView(session);
            }

            // Check if completed
            if (session.completed + session.failed >= session.total) {
                clearInterval(State.playlistPollInterval);
                localStorage.removeItem('playlist_download_session');
                UI.toast(
                    `Playlist complete! ${session.completed} of ${session.total} downloaded.`,
                    'success'
                );
                await loadHistory();
                if (session.playlist_id) {
                    await loadPlaylists(true);
                }
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

// ==================== Admin Panel ====================
let _adminUserSearchTimer = null;

function debounceAdminUserSearch() {
    clearTimeout(_adminUserSearchTimer);
    _adminUserSearchTimer = setTimeout(() => loadAdminUsers(1), 300);
}

let _serverStatusPollInterval = null;

function switchAdminTab(tab) {
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    document.getElementById('adminUsersPanel')?.classList.toggle('hidden', tab !== 'users');
    document.getElementById('adminAuditPanel')?.classList.toggle('hidden', tab !== 'audit');
    document.getElementById('adminCategoriesPanel')?.classList.toggle('hidden', tab !== 'categories');
    document.getElementById('adminServerPanel')?.classList.toggle('hidden', tab !== 'server');

    // Stop server polling when leaving the tab
    if (tab !== 'server' && _serverStatusPollInterval) {
        clearInterval(_serverStatusPollInterval);
        _serverStatusPollInterval = null;
    }

    if (tab === 'users') loadAdminUsers(1);
    else if (tab === 'audit') loadAuditLogs(1);
    else if (tab === 'categories') loadAdminCategories();
    else if (tab === 'server') startServerStatusPolling();
}

function startServerStatusPolling() {
    loadServerStatus();
    if (_serverStatusPollInterval) clearInterval(_serverStatusPollInterval);
    _serverStatusPollInterval = setInterval(loadServerStatus, 5000);
}

async function loadServerStatus() {
    try {
        const data = await API.admin.getServerStatus();
        renderServerStatus(data);
    } catch (error) {
        console.error('Failed to load server status:', error);
    }
}

function _statusColor(percent) {
    if (percent >= 90) return '#e74c3c';
    if (percent >= 70) return '#f39c12';
    return '#2ecc71';
}

function _formatBytes(mb) {
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
    return `${mb} MB`;
}

function renderServerStatus(data) {
    const grid = document.getElementById('serverStatusGrid');
    if (!grid) return;

    let cards = '';

    // ── Uptime Card ──
    if (data.uptime) {
        cards += `
            <div class="server-card server-card--wide">
                <div class="server-card__icon"><i class="fas fa-clock"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Uptime</div>
                    <div class="server-card__value">${data.uptime.formatted}</div>
                </div>
            </div>`;
    }

    // ── Platform Card ──
    if (data.platform) {
        cards += `
            <div class="server-card server-card--wide">
                <div class="server-card__icon"><i class="fas fa-microchip"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Platform</div>
                    <div class="server-card__value">${data.platform.os} ${data.platform.arch}</div>
                    <div class="server-card__sub">Python ${data.platform.python} · ${UI.escapeHtml(data.platform.hostname)}</div>
                </div>
            </div>`;
    }

    // ── CPU Card ──
    if (data.cpu) {
        const cpuColor = _statusColor(data.cpu.percent);
        cards += `
            <div class="server-card">
                <div class="server-card__icon" style="color:${cpuColor}"><i class="fas fa-tachometer-alt"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">CPU Usage</div>
                    <div class="server-card__value" style="color:${cpuColor}">${data.cpu.percent}%</div>
                    <div class="server-card__bar">
                        <div class="server-card__bar-fill" style="width:${data.cpu.percent}%;background:${cpuColor}"></div>
                    </div>
                    <div class="server-card__sub">${data.cpu.cores_logical} cores${data.cpu.frequency_mhz ? ' · ' + data.cpu.frequency_mhz + ' MHz' : ''}</div>
                </div>
            </div>`;
    }

    // ── Memory Card ──
    if (data.memory) {
        const memColor = _statusColor(data.memory.percent);
        cards += `
            <div class="server-card">
                <div class="server-card__icon" style="color:${memColor}"><i class="fas fa-memory"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Memory</div>
                    <div class="server-card__value" style="color:${memColor}">${data.memory.percent}%</div>
                    <div class="server-card__bar">
                        <div class="server-card__bar-fill" style="width:${data.memory.percent}%;background:${memColor}"></div>
                    </div>
                    <div class="server-card__sub">${_formatBytes(data.memory.used_mb)} / ${_formatBytes(data.memory.total_mb)}</div>
                </div>
            </div>`;
    }

    // ── Disk Card ──
    if (data.disk) {
        const diskColor = _statusColor(data.disk.percent);
        cards += `
            <div class="server-card">
                <div class="server-card__icon" style="color:${diskColor}"><i class="fas fa-hdd"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Disk Storage</div>
                    <div class="server-card__value" style="color:${diskColor}">${data.disk.percent}%</div>
                    <div class="server-card__bar">
                        <div class="server-card__bar-fill" style="width:${data.disk.percent}%;background:${diskColor}"></div>
                    </div>
                    <div class="server-card__sub">${data.disk.used_gb} GB / ${data.disk.total_gb} GB · ${data.disk.free_gb} GB free</div>
                </div>
            </div>`;
    }

    // ── Network Card ──
    if (data.network) {
        let netDetails = `↑ ${_formatBytes(data.network.bytes_sent_mb)} · ↓ ${_formatBytes(data.network.bytes_recv_mb)}`;
        if (data.network.active_connections != null) {
            netDetails += ` · ${data.network.active_connections} connections`;
        }
        let ifaceHtml = '';
        if (data.network.interfaces && data.network.interfaces.length) {
            ifaceHtml = '<div class="server-card__interfaces">' +
                data.network.interfaces.map(i =>
                    `<span class="server-iface"><i class="fas fa-ethernet"></i> ${UI.escapeHtml(i.name)}: <strong>${UI.escapeHtml(i.ip)}</strong></span>`
                ).join('') + '</div>';
        }
        cards += `
            <div class="server-card server-card--wide">
                <div class="server-card__icon"><i class="fas fa-network-wired"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Network I/O</div>
                    <div class="server-card__value-sm">${netDetails}</div>
                    ${ifaceHtml}
                </div>
            </div>`;
    }

    // ── Process Card ──
    if (data.process) {
        cards += `
            <div class="server-card">
                <div class="server-card__icon"><i class="fas fa-cogs"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Zora Process</div>
                    <div class="server-card__value-sm">PID ${data.process.pid}</div>
                    <div class="server-card__sub">
                        RAM: ${data.process.memory_rss_mb || '?'} MB · 
                        Threads: ${data.process.threads || '?'}${data.process.open_files != null ? ' · Files: ' + data.process.open_files : ''}
                    </div>
                </div>
            </div>`;
    }

    // ── Library Card ──
    if (data.library) {
        cards += `
            <div class="server-card">
                <div class="server-card__icon"><i class="fas fa-music"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Library</div>
                    <div class="server-card__value">${data.library.total_songs}</div>
                    <div class="server-card__sub">
                        ${_formatBytes(data.library.total_size_mb)} on disk · 
                        ${data.library.files_on_disk} files · 
                        DB: ${data.library.db_size_mb} MB
                    </div>
                </div>
            </div>`;
    }

    // ── Queue Card ──
    if (data.queue) {
        const qActive = data.queue.active || 0;
        const qQueued = data.queue.queued || 0;
        cards += `
            <div class="server-card">
                <div class="server-card__icon"><i class="fas fa-download"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Download Queue</div>
                    <div class="server-card__value">${qActive} active</div>
                    <div class="server-card__sub">${qQueued} queued</div>
                </div>
            </div>`;
    }

    // ── Users Card ──
    if (data.library) {
        cards += `
            <div class="server-card">
                <div class="server-card__icon"><i class="fas fa-users"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Users</div>
                    <div class="server-card__value">${data.library.total_users}</div>
                    <div class="server-card__sub">registered accounts</div>
                </div>
            </div>`;
    }

    // ── Load Average Card ──
    if (data.load_average) {
        cards += `
            <div class="server-card">
                <div class="server-card__icon"><i class="fas fa-chart-line"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Load Average</div>
                    <div class="server-card__value-sm">${data.load_average.load_1m} / ${data.load_average.load_5m} / ${data.load_average.load_15m}</div>
                    <div class="server-card__sub">1 min / 5 min / 15 min</div>
                </div>
            </div>`;
    }

    // ── Temperature Card ──
    if (data.temperature) {
        const tempColor = data.temperature.current_c >= 80 ? '#e74c3c' :
            data.temperature.current_c >= 60 ? '#f39c12' : '#2ecc71';
        cards += `
            <div class="server-card">
                <div class="server-card__icon" style="color:${tempColor}"><i class="fas fa-thermometer-half"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Temperature</div>
                    <div class="server-card__value" style="color:${tempColor}">${data.temperature.current_c}°C</div>
                    <div class="server-card__sub">${UI.escapeHtml(data.temperature.label)}${data.temperature.high_c ? ' · High: ' + data.temperature.high_c + '°C' : ''}</div>
                </div>
            </div>`;
    }

    // ── Server Time ──
    if (data.server_time) {
        const st = new Date(data.server_time);
        cards += `
            <div class="server-card">
                <div class="server-card__icon"><i class="fas fa-calendar-alt"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Server Time</div>
                    <div class="server-card__value-sm">${st.toLocaleString()}</div>
                </div>
            </div>`;
    }

    // ── psutil warning ──
    if (!data.has_psutil) {
        cards += `
            <div class="server-card server-card--wide server-card--warn">
                <div class="server-card__icon"><i class="fas fa-exclamation-triangle"></i></div>
                <div class="server-card__body">
                    <div class="server-card__label">Limited Metrics</div>
                    <div class="server-card__sub">Install <code>psutil</code> for CPU, memory, network, and temperature data:<br><code>pip install psutil</code></div>
                </div>
            </div>`;
    }

    grid.innerHTML = cards;
}

async function loadAdminUsers(page = 1) {
    const search = document.getElementById('adminUserSearch')?.value?.trim() || '';
    try {
        const data = await API.admin.getUsers(page, 20, search);
        renderAdminUsers(data);
    } catch (error) {
        UI.toast(error.message, 'error');
    }
}

function renderAdminUsers(data) {
    const tbody = document.getElementById('adminUsersBody');
    if (!tbody) return;

    if (!data.users.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="admin-empty">No users found</td></tr>';
        document.getElementById('adminUsersPagination').innerHTML = '';
        return;
    }

    tbody.innerHTML = data.users.map(u => `
        <tr>
            <td>
                <div class="admin-user-cell">
                    <div class="admin-avatar">${UI.escapeHtml((u.name || u.email || '?').charAt(0).toUpperCase())}</div>
                    <span>${UI.escapeHtml(u.name)}</span>
                </div>
            </td>
            <td>${UI.escapeHtml(u.email)}</td>
            <td>
                <select class="admin-role-select" onchange="changeUserRole(${u.id}, this.value)" ${u.id === State.user.id ? 'disabled' : ''}>
                    <option value="user" ${u.role === 'user' ? 'selected' : ''}>User</option>
                    <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
                </select>
            </td>
            <td>
                <span class="admin-badge admin-badge--${u.is_active ? 'active' : 'inactive'}">
                    ${u.is_active ? 'Active' : 'Inactive'}
                </span>
            </td>
            <td>${u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
            <td>${u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : 'Never'}</td>
            <td>
                ${u.id !== State.user.id ? `
                    <button class="btn btn--sm btn--${u.is_active ? 'danger' : 'success'}" onclick="toggleUserActive(${u.id}, ${!u.is_active})">
                        <i class="fas fa-${u.is_active ? 'ban' : 'check'}"></i>
                        ${u.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                ` : '<span class="admin-muted">You</span>'}
            </td>
        </tr>
    `).join('');

    renderPagination('adminUsersPagination', data, 'loadAdminUsers');
}

async function changeUserRole(userId, newRole) {
    try {
        await API.admin.updateUser(userId, { role: newRole });
        UI.toast('Role updated', 'success');
        loadAdminUsers();
    } catch (error) {
        UI.toast(error.message, 'error');
        loadAdminUsers();
    }
}

async function toggleUserActive(userId, active) {
    try {
        await API.admin.updateUser(userId, { is_active: active });
        UI.toast(active ? 'User activated' : 'User deactivated', 'success');
        loadAdminUsers();
    } catch (error) {
        UI.toast(error.message, 'error');
        loadAdminUsers();
    }
}

async function loadAuditLogs(page = 1) {
    const action = document.getElementById('adminAuditFilter')?.value || '';
    try {
        const data = await API.admin.getAuditLogs(page, 30, action);
        renderAuditLogs(data);
    } catch (error) {
        UI.toast(error.message, 'error');
    }
}

function renderAuditLogs(data) {
    const tbody = document.getElementById('adminAuditBody');
    if (!tbody) return;

    if (!data.logs.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="admin-empty">No audit logs found</td></tr>';
        document.getElementById('adminAuditPagination').innerHTML = '';
        return;
    }

    tbody.innerHTML = data.logs.map(log => {
        const meta = log.metadata ? Object.entries(log.metadata).map(([k, v]) => `${k}: ${v}`).join(', ') : '—';
        return `
            <tr>
                <td>${log.created_at ? new Date(log.created_at).toLocaleString() : '—'}</td>
                <td>${UI.escapeHtml(log.actor_name || '—')}</td>
                <td><span class="admin-action-badge">${UI.escapeHtml(log.action)}</span></td>
                <td>${log.target_type ? `${UI.escapeHtml(log.target_type)}${log.target_id ? ' #' + UI.escapeHtml(log.target_id) : ''}` : '—'}</td>
                <td class="admin-meta-cell">${UI.escapeHtml(meta)}</td>
                <td>${UI.escapeHtml(log.ip_address || '—')}</td>
            </tr>
        `;
    }).join('');

    renderPagination('adminAuditPagination', data, 'loadAuditLogs');
}

function renderPagination(containerId, data, loadFn) {
    const container = document.getElementById(containerId);
    if (!container || data.pages <= 1) {
        if (container) container.innerHTML = '';
        return;
    }

    let html = '';
    if (data.page > 1) {
        html += `<button class="btn btn--sm" onclick="${loadFn}(${data.page - 1})"><i class="fas fa-chevron-left"></i></button>`;
    }
    html += `<span class="admin-page-info">Page ${data.page} of ${data.pages}</span>`;
    if (data.page < data.pages) {
        html += `<button class="btn btn--sm" onclick="${loadFn}(${data.page + 1})"><i class="fas fa-chevron-right"></i></button>`;
    }
    container.innerHTML = html;
}

// ==================== Admin Categories ====================

async function loadAdminCategories() {
    try {
        const categories = await API.categories.list();
        State.categories = categories;
        renderAdminCategories(categories);
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

function renderAdminCategories(categories) {
    const container = document.getElementById('adminCategoriesList');
    if (!container) return;

    if (!categories.length) {
        container.innerHTML = `<div class="empty-state"><i class="fas fa-tags"></i><h3>No categories</h3><p>Create categories for users to organize playlists</p></div>`;
        return;
    }

    container.innerHTML = categories.map(cat => `
        <div class="admin-category-item">
            <div class="admin-category-item__preview" style="background: ${UI.escapeHtml(cat.color)}">
                <i class="fas ${UI.escapeHtml(cat.icon)}"></i>
            </div>
            <div class="admin-category-item__info">
                <span class="admin-category-item__name">${UI.escapeHtml(cat.name)}</span>
                <span class="admin-category-item__meta">Icon: ${UI.escapeHtml(cat.icon)} · Order: ${cat.sort_order}</span>
            </div>
            <div class="admin-category-item__actions">
                <button class="btn btn--danger btn--sm" onclick="deleteCategory(${cat.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

function openCreateCategoryForm() {
    document.getElementById('categoryCreateForm')?.classList.remove('hidden');
    document.getElementById('newCategoryName')?.focus();
}

function closeCategoryForm() {
    document.getElementById('categoryCreateForm')?.classList.add('hidden');
}

async function createCategory() {
    const name = document.getElementById('newCategoryName')?.value.trim();
    const icon = document.getElementById('newCategoryIcon')?.value.trim() || 'fa-music';
    const color = document.getElementById('newCategoryColor')?.value || '#6C5CE7';

    if (!name) {
        UI.toast('Category name is required', 'error');
        return;
    }

    try {
        await API.categories.create({ name, icon, color });
        UI.toast('Category created', 'success');
        document.getElementById('newCategoryName').value = '';
        closeCategoryForm();
        loadAdminCategories();
        _categoriesLoaded = false; // force refresh of filter bar
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

async function deleteCategory(categoryId) {
    if (!confirm('Delete this category? Playlists using it will become uncategorized.')) return;

    try {
        await API.categories.delete(categoryId);
        UI.toast('Category deleted', 'success');
        loadAdminCategories();
        _categoriesLoaded = false;
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}
