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
        const response = await fetch('/api/playlist-download/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                songs: selectedSongs,
                create_playlist: autoCreatePlaylist,
                playlist_name: playlistName
            })
        });

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
            const response = await fetch(
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

function switchAdminTab(tab) {
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    document.getElementById('adminUsersPanel')?.classList.toggle('hidden', tab !== 'users');
    document.getElementById('adminAuditPanel')?.classList.toggle('hidden', tab !== 'audit');
    document.getElementById('adminCategoriesPanel')?.classList.toggle('hidden', tab !== 'categories');

    if (tab === 'users') loadAdminUsers(1);
    else if (tab === 'audit') loadAuditLogs(1);
    else if (tab === 'categories') loadAdminCategories();
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
