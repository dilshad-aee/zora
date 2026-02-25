/**
 * Zora - Playlists Module (v2)
 * Explore, My Playlists, Playlist Detail, Likes, Categories
 *
 * Dependencies: api.js, ui.js, player.js, app.js (State, openConfirmAction, loadHistory)
 *               library.js (updateLibrary), playback.js (getCurrentPlaybackSongId, buildSelectedPlaylistPlaybackQueue, setPlaybackQueue, playFromCurrentQueue, prunePlaybackQueueAfterDelete)
 */

// State
let _playlistActiveTab = 'explore'; // 'explore' | 'mine' | 'detail'
let _playlistDetailSource = 'explore'; // which tab opened the detail
let _selectedCategoryId = null;
let _categoriesLoaded = false;

// ==================== Tab Navigation ====================

function switchPlaylistTab(tab) {
    _playlistActiveTab = tab;

    // Update tab buttons
    document.querySelectorAll('.playlist-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Show/hide tab content
    const tabs = { explore: 'playlistTabExplore', mine: 'playlistTabMine', detail: 'playlistTabDetail' };
    Object.entries(tabs).forEach(([key, id]) => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('hidden', key !== tab);
    });

    // Load data for the tab
    if (tab === 'explore') {
        loadExplorePlaylists();
        loadCategoryFilterBar();
    } else if (tab === 'mine') {
        loadMyPlaylists();
    }
}

function goBackFromPlaylistDetail() {
    switchPlaylistTab(_playlistDetailSource || 'explore');
}

// ==================== Explore ====================

async function loadExplorePlaylists(page = 1) {
    const sortEl = document.getElementById('exploreSortSelect');
    const sort = sortEl ? sortEl.value : 'recent';

    try {
        const data = await API.explorePlaylists({
            category: _selectedCategoryId || undefined,
            sort,
            page,
        });

        renderPlaylistGrid('exploreGrid', data.playlists || [], { showOwner: true });
        renderExplorePagination(data);
    } catch (err) {
        console.warn('Failed to load explore playlists:', err.message);
    }
}

function filterByCategory(categoryId) {
    _selectedCategoryId = categoryId;

    // Update pill active states
    document.querySelectorAll('.category-pill').forEach(pill => {
        const pillCat = pill.dataset.category;
        pill.classList.toggle('active', pillCat === String(categoryId || ''));
    });

    loadExplorePlaylists();
}

function renderExplorePagination(data) {
    const container = document.getElementById('explorePagination');
    if (!container) return;

    if (!data.pages || data.pages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '<div class="pagination">';
    for (let i = 1; i <= data.pages; i++) {
        html += `<button class="pagination__btn ${i === data.page ? 'active' : ''}" 
                  onclick="loadExplorePlaylists(${i})">${i}</button>`;
    }
    html += '</div>';
    container.innerHTML = html;
}

// ==================== Category Filter Bar ====================

async function loadCategoryFilterBar() {
    if (_categoriesLoaded) return;

    try {
        const categories = await API.categories.list();
        State.categories = categories;
        _categoriesLoaded = true;
        renderCategoryFilterBar(categories);
    } catch (err) {
        console.warn('Could not load categories:', err.message);
    }
}

function renderCategoryFilterBar(categories) {
    const bar = document.getElementById('categoryFilterBar');
    if (!bar) return;

    let html = `<button class="category-pill active" data-category="" onclick="filterByCategory(null)">
        <i class="fas fa-globe"></i> All
    </button>`;

    (categories || []).forEach(cat => {
        html += `<button class="category-pill" data-category="${cat.id}" 
                  onclick="filterByCategory(${cat.id})"
                  style="--pill-color: ${UI.escapeHtml(cat.color)}">
            <i class="fas ${UI.escapeHtml(cat.icon)}"></i> ${UI.escapeHtml(cat.name)}
        </button>`;
    });

    bar.innerHTML = html;
}

// ==================== My Playlists ====================

async function loadMyPlaylists() {
    try {
        const playlists = await API.getPlaylists();
        State.playlists.list = playlists;
        renderPlaylistGrid('myPlaylistsGrid', playlists, { showOwner: false, isOwner: true });
    } catch (err) {
        console.warn('Failed to load my playlists:', err.message);
    }
}

// Keep backward compat
async function loadPlaylists(keepSelection = true) {
    try {
        const playlists = await API.getPlaylists();
        State.playlists.list = playlists;
        if (_playlistActiveTab === 'mine') {
            renderPlaylistGrid('myPlaylistsGrid', playlists, { showOwner: false, isOwner: true });
        }
    } catch (err) {
        console.warn('Failed to load playlists:', err.message);
    }
}

// ==================== Playlist Card Grid ====================

function renderPlaylistGrid(containerId, playlists, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!playlists.length) {
        const icon = containerId === 'exploreGrid' ? 'fa-compass' : 'fa-folder-open';
        const title = containerId === 'exploreGrid' ? 'No public playlists yet' : 'No playlists yet';
        const desc = containerId === 'exploreGrid' ? 'Be the first to create a public playlist!' : 'Create a playlist to organize your downloads';
        container.innerHTML = `<div class="empty-state"><i class="fas ${icon}"></i><h3>${title}</h3><p>${desc}</p></div>`;
        return;
    }

    container.innerHTML = playlists.map(pl => renderPlaylistCard(pl, options)).join('');
}

function renderPlaylistCard(pl, options = {}) {
    const catBadge = pl.category
        ? `<span class="playlist-card__cat" style="--cat-color: ${UI.escapeHtml(pl.category.color)}">
            <i class="fas ${UI.escapeHtml(pl.category.icon)}"></i> ${UI.escapeHtml(pl.category.name)}
           </span>`
        : '';

    const ownerLine = options.showOwner
        ? `<span class="playlist-card__owner">by ${UI.escapeHtml(pl.owner_name)}</span>`
        : '';

    const visibilityIcon = pl.visibility === 'public'
        ? '<i class="fas fa-globe playlist-card__vis" title="Public"></i>'
        : '<i class="fas fa-lock playlist-card__vis" title="Private"></i>';

    const liked = pl.liked ? 'liked' : '';
    const likeIcon = pl.liked ? 'fas' : 'far';

    return `
    <div class="playlist-card" onclick="openPlaylistDetail(${pl.id})">
        <div class="playlist-card__cover">
            <i class="fas fa-compact-disc playlist-card__cover-icon"></i>
            <span class="playlist-card__count">${pl.song_count} <i class="fas fa-music"></i></span>
        </div>
        <div class="playlist-card__body">
            <h3 class="playlist-card__name">${UI.escapeHtml(pl.name)} ${visibilityIcon}</h3>
            ${ownerLine}
            ${pl.description ? `<p class="playlist-card__desc">${UI.escapeHtml(pl.description.substring(0, 80))}</p>` : ''}
            <div class="playlist-card__footer">
                ${catBadge}
                <button class="playlist-card__like ${liked}" 
                        onclick="event.stopPropagation(); toggleLike(${pl.id}, this)" title="Like">
                    <i class="${likeIcon} fa-heart"></i>
                    <span>${pl.like_count || 0}</span>
                </button>
            </div>
        </div>
    </div>`;
}

// ==================== Playlist Detail ====================

async function openPlaylistDetail(playlistId) {
    _playlistDetailSource = _playlistActiveTab;

    // Show detail tab
    _playlistActiveTab = 'detail';
    document.querySelectorAll('.playlist-tab').forEach(btn => btn.classList.remove('active'));
    document.getElementById('playlistTabExplore')?.classList.add('hidden');
    document.getElementById('playlistTabMine')?.classList.add('hidden');
    document.getElementById('playlistTabDetail')?.classList.remove('hidden');

    try {
        const data = await API.getPlaylistSongs(playlistId);
        const pl = data.playlist;
        State.playlists.selectedId = pl.id;
        State.playlists.songs = data.songs;

        renderPlaylistDetailHeader(pl, data.is_owner);
        renderPlaylistDetailSongs(data.songs, data.is_owner);
        updatePlaylistPlaybackControls();
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

function _formatTotalDuration(songs) {
    const totalSec = (songs || []).reduce((sum, s) => sum + (s.duration || 0), 0);
    if (!totalSec) return '';
    const hrs = Math.floor(totalSec / 3600);
    const mins = Math.floor((totalSec % 3600) / 60);
    if (hrs > 0) return `${hrs} hr ${mins} min`;
    return `${mins} min`;
}

function renderPlaylistDetailHeader(pl, isOwner) {
    const header = document.getElementById('playlistDetailHeader');
    if (!header) return;

    const songs = State.playlists.songs || [];
    const totalDuration = _formatTotalDuration(songs);

    const catBadge = pl.category
        ? `<span class="detail-cat-badge" style="--cat-color: ${UI.escapeHtml(pl.category.color)}">
            <i class="fas ${UI.escapeHtml(pl.category.icon)}"></i> ${UI.escapeHtml(pl.category.name)}
           </span>`
        : '';

    const liked = pl.liked ? 'liked' : '';
    const likeIcon = pl.liked ? 'fas' : 'far';

    const ownerActions = isOwner ? `
        <button class="btn btn--secondary btn--small" onclick="openAddSongsToSelectedPlaylistModal()">
            <i class="fas fa-plus"></i> <span class="btn-text">Add Songs</span>
        </button>
        <button class="btn btn--secondary btn--small" onclick="openEditPlaylistModal(${pl.id})">
            <i class="fas fa-edit"></i> <span class="btn-text">Edit</span>
        </button>
        <button class="btn btn--danger btn--small" onclick="deleteSelectedPlaylist()">
            <i class="fas fa-trash"></i> <span class="btn-text">Delete</span>
        </button>` : '';

    header.innerHTML = `
        <div class="playlist-detail__info">
            <div class="playlist-detail__icon">
                <i class="fas fa-compact-disc"></i>
            </div>
            <div class="playlist-detail__meta">
                <h2 class="playlist-detail__title">${UI.escapeHtml(pl.name)}</h2>
                <p class="playlist-detail__byline">
                    <span>by ${UI.escapeHtml(pl.owner_name)}</span>
                    <span class="playlist-detail__stats">
                        ${songs.length} songs${totalDuration ? ' · ' + totalDuration : ''} · 
                        <span class="playlist-detail__vis">
                            ${pl.visibility === 'public' ? '<i class="fas fa-globe"></i> Public' : '<i class="fas fa-lock"></i> Private'}
                        </span>
                    </span>
                </p>
                ${pl.description ? `<p class="playlist-detail__desc">${UI.escapeHtml(pl.description)}</p>` : ''}
                <div class="playlist-detail__tags">
                    ${catBadge}
                    <button class="playlist-detail__like-btn ${liked}" 
                            onclick="toggleLike(${pl.id}, this)">
                        <i class="${likeIcon} fa-heart"></i>
                        <span>${pl.like_count || 0}</span>
                    </button>
                </div>
            </div>
        </div>
        <div class="playlist-detail__actions">${ownerActions}</div>
    `;
}

function renderPlaylistDetailSongs(songs, isOwner) {
    const container = document.getElementById('playlistSongsList');
    if (!container) return;

    if (!songs || !songs.length) {
        container.innerHTML = `<div class="empty-state"><i class="fas fa-music"></i><h3>No songs yet</h3><p>${isOwner ? 'Add songs from your library' : 'This playlist is empty'}</p></div>`;
        return;
    }

    const currentSongId = getCurrentPlaybackSongId?.() || null;
    container.innerHTML = songs.map((song, i) => {
        const isPlaying = currentSongId === song.id;
        const duration = song.duration ? UI.formatTime(song.duration) : '';

        return `
        <div class="playlist-song-row ${isPlaying ? 'playing' : ''}" 
             onclick="playPlaylistSong(${song.id})">
            <div class="playlist-song-row__num">${isPlaying ? '<i class="fas fa-volume-up"></i>' : i + 1}</div>
            <img src="${song.thumbnail || '/static/images/default-album.png'}" 
                 alt="" class="playlist-song-row__thumb" onerror="this.src='/static/images/default-album.png'">
            <div class="playlist-song-row__info">
                <span class="playlist-song-row__title">${UI.escapeHtml(song.title || 'Unknown')}</span>
                <span class="playlist-song-row__artist">${UI.escapeHtml(song.artist || song.uploader || 'Unknown')}</span>
            </div>
            ${duration ? `<span class="playlist-song-row__duration">${duration}</span>` : ''}
            <div class="playlist-song-row__actions">
                <button class="btn btn--icon btn--small song-menu-trigger" 
                        onclick="event.stopPropagation(); toggleSongMenu(${song.id}, ${isOwner}, this)"
                        title="More options">
                    <i class="fas fa-ellipsis-v"></i>
                </button>
            </div>
        </div>`;
    }).join('');
}

// ==================== Song Context Menu ====================

let _activeSongMenu = null;

function toggleSongMenu(downloadId, isOwner, triggerBtn) {
    // Close any existing menu
    closeSongMenu();

    const removeOption = isOwner
        ? `<button class="song-ctx-menu__item song-ctx-menu__item--danger" 
                  onclick="event.stopPropagation(); closeSongMenu(); removeSongFromSelectedPlaylist(${downloadId})">
              <i class="fas fa-times-circle"></i> Remove from playlist
           </button>`
        : '';

    const menu = document.createElement('div');
    menu.className = 'song-ctx-menu';
    menu.innerHTML = `
        <button class="song-ctx-menu__item" 
                onclick="event.stopPropagation(); closeSongMenu(); openAddSongToAnotherPlaylist(${downloadId})">
            <i class="fas fa-list-ul"></i> Add to another playlist
        </button>
        ${removeOption}
    `;

    // Position relative to the trigger button
    triggerBtn.parentElement.style.position = 'relative';
    triggerBtn.parentElement.appendChild(menu);
    _activeSongMenu = menu;

    // Close on outside click
    setTimeout(() => {
        document.addEventListener('click', _closeSongMenuOnOutsideClick, { once: true });
    }, 0);
}

function closeSongMenu() {
    if (_activeSongMenu) {
        _activeSongMenu.remove();
        _activeSongMenu = null;
    }
    document.removeEventListener('click', _closeSongMenuOnOutsideClick);
}

function _closeSongMenuOnOutsideClick(e) {
    if (_activeSongMenu && !_activeSongMenu.contains(e.target)) {
        closeSongMenu();
    }
}

function openAddSongToAnotherPlaylist(downloadId) {
    // Show a small modal to pick which playlist
    const playlists = (State.playlists.list || []).filter(
        p => p.id !== State.playlists.selectedId // exclude current playlist
    );

    if (!playlists.length) {
        UI.toast('No other playlists to add to. Create one first!', 'error');
        return;
    }

    const options = playlists.map(pl => `
        <button class="add-to-playlist-option" onclick="addSongToOtherPlaylist(${pl.id}, ${downloadId})">
            <i class="fas fa-list"></i>
            <span>${UI.escapeHtml(pl.name)}</span>
            <span class="text-muted">${pl.song_count} songs</span>
        </button>
    `).join('');

    const html = `
    <div class="modal-overlay" id="addToOtherPlaylistModal" onclick="if(event.target===event.currentTarget)closeAddToOtherPlaylistModal()">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal__header">
                <h2><i class="fas fa-list-ul"></i> Add to Playlist</h2>
                <button class="modal__close" onclick="closeAddToOtherPlaylistModal()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal__body">
                <div class="add-to-playlist-options">${options}</div>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
}

function closeAddToOtherPlaylistModal() {
    document.getElementById('addToOtherPlaylistModal')?.remove();
}

async function addSongToOtherPlaylist(playlistId, downloadId) {
    try {
        await API.addSongToPlaylist(playlistId, downloadId);
        UI.toast('Added to playlist!', 'success');
        closeAddToOtherPlaylistModal();
        bumpPlaylistSongCount(playlistId, 1);
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

// ==================== Likes ====================

async function toggleLike(playlistId, btn) {
    const isLiked = btn.classList.contains('liked');
    const icon = btn.querySelector('i');
    const countSpan = btn.querySelector('span');
    const currentCount = parseInt(countSpan?.textContent || '0');

    // Optimistic UI
    if (isLiked) {
        btn.classList.remove('liked');
        icon.className = 'far fa-heart';
        if (countSpan) countSpan.textContent = Math.max(0, currentCount - 1);
    } else {
        btn.classList.add('liked');
        icon.className = 'fas fa-heart';
        if (countSpan) countSpan.textContent = currentCount + 1;
    }

    try {
        const result = isLiked
            ? await API.unlikePlaylist(playlistId)
            : await API.likePlaylist(playlistId);

        // Sync actual count from server
        if (countSpan && result.like_count !== undefined) {
            countSpan.textContent = result.like_count;
        }
    } catch (err) {
        // Revert on error
        if (isLiked) {
            btn.classList.add('liked');
            icon.className = 'fas fa-heart';
        } else {
            btn.classList.remove('liked');
            icon.className = 'far fa-heart';
        }
        if (countSpan) countSpan.textContent = currentCount;
        UI.toast(err.message, 'error');
    }
}

// ==================== Create Playlist Modal ====================

function openCreatePlaylistModal() {
    // Build category options
    const cats = State.categories || [];
    const catOptions = cats.map(c =>
        `<option value="${c.id}">${UI.escapeHtml(c.name)}</option>`
    ).join('');

    const html = `
    <div class="modal-overlay" id="createPlaylistModal" onclick="closeCreatePlaylistModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal__header">
                <h2><i class="fas fa-plus"></i> New Playlist</h2>
                <button class="modal__close" onclick="closeCreatePlaylistModal()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal__body">
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" id="createPlaylistNameInput" class="form-input" placeholder="Playlist name" maxlength="120" autofocus>
                </div>
                <div class="form-group">
                    <label>Description (optional)</label>
                    <textarea id="createPlaylistDescInput" class="form-input form-textarea" placeholder="What's this playlist about?" maxlength="500" rows="2"></textarea>
                </div>
                <div class="form-row">
                    <div class="form-group" style="flex:1">
                        <label>Visibility</label>
                        <select id="createPlaylistVisibility" class="form-input">
                            <option value="private">🔒 Private</option>
                            <option value="public">🌐 Public</option>
                        </select>
                    </div>
                    <div class="form-group" style="flex:1">
                        <label>Category</label>
                        <select id="createPlaylistCategory" class="form-input">
                            <option value="">None</option>
                            ${catOptions}
                        </select>
                    </div>
                </div>
                <button class="btn btn--primary btn--full" onclick="submitCreatePlaylist()">
                    <i class="fas fa-check"></i> Create Playlist
                </button>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
    document.getElementById('createPlaylistNameInput')?.focus();
}

function closeCreatePlaylistModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('createPlaylistModal')?.remove();
}

async function submitCreatePlaylist() {
    const name = document.getElementById('createPlaylistNameInput')?.value.trim();
    const description = document.getElementById('createPlaylistDescInput')?.value.trim();
    const visibility = document.getElementById('createPlaylistVisibility')?.value || 'private';
    const category_id = document.getElementById('createPlaylistCategory')?.value || null;

    if (!name) {
        UI.toast('Please enter a playlist name', 'error');
        return;
    }

    try {
        const pl = await API.createPlaylist({ name, description, visibility, category_id: category_id || undefined });
        // Push directly into local state so it shows immediately
        if (!Array.isArray(State.playlists.list)) State.playlists.list = [];
        State.playlists.list.unshift(pl);
        UI.toast('Playlist created!', 'success');
        closeCreatePlaylistModal();
        // Switch to My Playlists tab and render
        switchPlaylistTab('mine');
        if (visibility === 'public') loadExplorePlaylists();
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

// ==================== Edit Playlist Modal ====================

function openEditPlaylistModal(playlistId) {
    const pl = (State.playlists.list || []).find(p => p.id === playlistId);
    if (!pl) return;

    const cats = State.categories || [];
    const catOptions = cats.map(c =>
        `<option value="${c.id}" ${c.id === pl.category_id ? 'selected' : ''}>${UI.escapeHtml(c.name)}</option>`
    ).join('');

    const html = `
    <div class="modal-overlay" id="editPlaylistModal" onclick="closeEditPlaylistModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal__header">
                <h2><i class="fas fa-edit"></i> Edit Playlist</h2>
                <button class="modal__close" onclick="closeEditPlaylistModal()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal__body">
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" id="editPlaylistNameInput" class="form-input" value="${UI.escapeHtml(pl.name)}" maxlength="120">
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="editPlaylistDescInput" class="form-input form-textarea" maxlength="500" rows="2">${UI.escapeHtml(pl.description || '')}</textarea>
                </div>
                <div class="form-row">
                    <div class="form-group" style="flex:1">
                        <label>Visibility</label>
                        <select id="editPlaylistVisibility" class="form-input">
                            <option value="private" ${pl.visibility === 'private' ? 'selected' : ''}>🔒 Private</option>
                            <option value="public" ${pl.visibility === 'public' ? 'selected' : ''}>🌐 Public</option>
                        </select>
                    </div>
                    <div class="form-group" style="flex:1">
                        <label>Category</label>
                        <select id="editPlaylistCategory" class="form-input">
                            <option value="">None</option>
                            ${catOptions}
                        </select>
                    </div>
                </div>
                <button class="btn btn--primary btn--full" onclick="submitEditPlaylist(${playlistId})">
                    <i class="fas fa-save"></i> Save Changes
                </button>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
}

function closeEditPlaylistModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('editPlaylistModal')?.remove();
}

async function submitEditPlaylist(playlistId) {
    const name = document.getElementById('editPlaylistNameInput')?.value.trim();
    const description = document.getElementById('editPlaylistDescInput')?.value.trim();
    const visibility = document.getElementById('editPlaylistVisibility')?.value;
    const category_id = document.getElementById('editPlaylistCategory')?.value || null;

    if (!name) {
        UI.toast('Playlist name is required', 'error');
        return;
    }

    try {
        await API.updatePlaylist(playlistId, { name, description, visibility, category_id });
        UI.toast('Playlist updated!', 'success');
        closeEditPlaylistModal();
        loadMyPlaylists();
        openPlaylistDetail(playlistId);
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

// ==================== Delete Playlist ====================

async function deleteSelectedPlaylist() {
    const playlistId = State.playlists.selectedId;
    if (!playlistId) return;

    const confirmed = await openConfirmAction({
        title: 'Delete Playlist',
        message: 'All songs will be removed from this playlist. This cannot be undone.',
        confirmLabel: 'Delete',
        danger: true,
    });
    if (!confirmed) return;

    try {
        await API.deletePlaylist(playlistId);
        UI.toast('Playlist deleted', 'success');
        State.playlists.selectedId = null;
        State.playlists.songs = [];
        goBackFromPlaylistDetail();
        loadMyPlaylists();
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

// ==================== Song Management (kept from v1) ====================

async function removeSongFromSelectedPlaylist(downloadId) {
    const playlistId = State.playlists.selectedId;
    if (!playlistId || !downloadId) return;

    try {
        await API.removeSongFromPlaylist(playlistId, downloadId);
        State.playlists.songs = State.playlists.songs.filter(s => s.id !== downloadId);
        renderPlaylistDetailSongs(State.playlists.songs, true);
        bumpPlaylistSongCount(playlistId, -1);
        prunePlaybackQueueAfterDelete?.(downloadId);
        updatePlaylistPlaybackControls();
        UI.toast('Song removed', 'success');
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

// ==================== Add-to-playlist modal (from library context menu) ====================

function openAddToPlaylistModal(event, downloadId) {
    event?.stopPropagation();
    State.playlists.pendingDownloadId = downloadId;
    const modal = document.getElementById('addToPlaylistModal');
    if (modal) {
        modal.classList.remove('hidden');
        renderAddToPlaylistOptions();
    }
}

function closeAddToPlaylistModal() {
    document.getElementById('addToPlaylistModal')?.classList.add('hidden');
}

function closeAddToPlaylistModalOnOverlay(event) {
    if (event.target === event.currentTarget) closeAddToPlaylistModal();
}

function renderAddToPlaylistOptions() {
    const container = document.getElementById('addToPlaylistOptions');
    if (!container) return;

    const playlists = State.playlists.list || [];
    if (!playlists.length) {
        container.innerHTML = '<p class="text-muted">No playlists yet. Create one first.</p>';
        return;
    }

    container.innerHTML = playlists.map(pl => `
        <button class="add-to-playlist-option" onclick="addCurrentSongToPlaylist(${pl.id})">
            <i class="fas fa-list"></i>
            <span>${UI.escapeHtml(pl.name)}</span>
            <span class="text-muted">${pl.song_count} songs</span>
        </button>
    `).join('');
}

async function addCurrentSongToPlaylist(playlistId) {
    const downloadId = State.playlists.pendingDownloadId;
    if (!downloadId) return;

    try {
        await API.addSongToPlaylist(playlistId, downloadId);
        UI.toast('Added to playlist', 'success');
        closeAddToPlaylistModal();
        bumpPlaylistSongCount(playlistId, 1);
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

// ==================== Add Songs to Selected Playlist (bulk modal) ====================

let _addSongsSearchQuery = '';

function getSelectedPlaylistSongIdSet() {
    const songs = State.playlists.songs || [];
    return new Set(songs.map(s => Number(s.id)).filter(Number.isFinite));
}

function normalizeSearchText(value) {
    return String(value || '').trim().toLowerCase()
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function getLibrarySongsForPlaylistModal(searchQuery = '') {
    const downloads = State.downloads || [];
    if (!searchQuery) return downloads;
    const q = normalizeSearchText(searchQuery);
    return downloads.filter(d => {
        const text = normalizeSearchText(`${d.title} ${d.artist || d.uploader || ''}`);
        return text.includes(q);
    });
}

function openAddSongsToSelectedPlaylistModal() {
    _addSongsSearchQuery = '';
    const html = `
    <div class="modal-overlay" id="addSongsModal" onclick="if(event.target===event.currentTarget)closeAddSongsModal()">
        <div class="modal modal--wide" onclick="event.stopPropagation()">
            <div class="modal__header">
                <h2><i class="fas fa-plus"></i> Add Songs</h2>
                <button class="modal__close" onclick="closeAddSongsModal()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal__body">
                <div class="library-search" style="margin-bottom: 1rem">
                    <div class="library-search__input-wrapper">
                        <i class="fas fa-search"></i>
                        <input type="text" id="addSongsSearchInput" placeholder="Search library..." oninput="onAddSongsSearchInput(this.value)">
                    </div>
                </div>
                <div id="addSongsListContainer" class="add-songs-list"></div>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
    renderAddSongsToPlaylistList();
}

function closeAddSongsModal() {
    document.getElementById('addSongsModal')?.remove();
}

function onAddSongsSearchInput(value) {
    _addSongsSearchQuery = value;
    renderAddSongsToPlaylistList();
}

function renderAddSongsToPlaylistList() {
    const container = document.getElementById('addSongsListContainer');
    if (!container) return;

    const existing = getSelectedPlaylistSongIdSet();
    const songs = getLibrarySongsForPlaylistModal(_addSongsSearchQuery);

    if (!songs.length) {
        container.innerHTML = '<p class="text-muted">No songs found.</p>';
        return;
    }

    container.innerHTML = songs.map(song => {
        const inPlaylist = existing.has(Number(song.id));
        return `
        <div class="add-songs-item ${inPlaylist ? 'in-playlist' : ''}">
            <img src="${song.thumbnail || '/static/images/default-album.png'}" 
                 alt="" class="add-songs-item__thumb" onerror="this.src='/static/images/default-album.png'">
            <div class="add-songs-item__info">
                <span class="add-songs-item__title">${UI.escapeHtml(song.title || 'Unknown')}</span>
                <span class="add-songs-item__artist">${UI.escapeHtml(song.artist || song.uploader || 'Unknown')}</span>
            </div>
            <button class="btn btn--small ${inPlaylist ? 'btn--secondary' : 'btn--primary'}" 
                    ${inPlaylist ? 'disabled' : ''} 
                    onclick="addSongToSelectedPlaylistFromModal(${song.id}, this)">
                ${inPlaylist ? '<i class="fas fa-check"></i>' : '<i class="fas fa-plus"></i> Add'}
            </button>
        </div>`;
    }).join('');
}

async function addSongToSelectedPlaylistFromModal(downloadId, btn) {
    const playlistId = State.playlists.selectedId;
    if (!playlistId) return;

    try {
        const result = await API.addSongToPlaylist(playlistId, downloadId);
        if (result.song) {
            State.playlists.songs.push(result.song);
        }
        // Update button
        if (btn) {
            btn.outerHTML = '<button class="btn btn--small btn--secondary" disabled><i class="fas fa-check"></i></button>';
        }
        bumpPlaylistSongCount(playlistId, 1);
        renderPlaylistDetailSongs(State.playlists.songs, true);
        updatePlaylistPlaybackControls();
        UI.toast('Song added', 'success');
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

function bumpPlaylistSongCount(playlistId, delta = 1) {
    const list = State.playlists.list || [];
    const pl = list.find(p => p.id === playlistId);
    if (pl) {
        pl.song_count = Math.max(0, (pl.song_count || 0) + delta);
    }
}

// ==================== Backward Compat / Helpers ====================

function getSelectedPlaylist() {
    return (State.playlists.list || []).find(p => p.id === State.playlists.selectedId) || null;
}

// Old functions mapped for backward compat
function renderPlaylistsList() { loadMyPlaylists(); }
function renderSelectedPlaylistPanel() {
    if (State.playlists.selectedId) {
        renderPlaylistDetailSongs(State.playlists.songs, true);
    }
}
function selectPlaylist(id) { openPlaylistDetail(id); }
function filterPlaylistsList(value) { /* no-op for now */ }
function switchPlaylistWorkspace(panel) { /* no-op - old UI */ }
function loadSelectedPlaylistSongs() { /* no-op - handled by detail */ }

// Old createPlaylist wrapper (for backward compat with playlist download flow)
async function createPlaylist() {
    const input = document.getElementById('newPlaylistName');
    const name = input?.value.trim();
    if (!name) {
        openCreatePlaylistModal();
        return;
    }
    try {
        const pl = await API.createPlaylist({ name });
        if (!Array.isArray(State.playlists.list)) State.playlists.list = [];
        State.playlists.list.unshift(pl);
        UI.toast(`Playlist "${pl.name}" created`, 'success');
        if (input) input.value = '';
        renderPlaylistGrid('myPlaylistsGrid', State.playlists.list, { showOwner: false, isOwner: true });
        return pl;
    } catch (err) {
        UI.toast(err.message, 'error');
    }
}

function createPlaylistFromModal() { createPlaylist(); }

// ==================== Playback Controls ====================

function updatePlaylistPlaybackControls() {
    const songs = State.playlists.songs || [];
    const hasSongs = songs.length > 0;
    const playAllBtn = document.getElementById('playlistPlayAllBtn');
    const shuffleBtn = document.getElementById('playlistShuffleBtn');
    const loopBtn = document.getElementById('playlistLoopBtn');

    if (playAllBtn) playAllBtn.disabled = !hasSongs;
    if (shuffleBtn) {
        shuffleBtn.disabled = !hasSongs;
        shuffleBtn.classList.toggle('active', Player.shuffle);
    }
    if (loopBtn) {
        loopBtn.disabled = !hasSongs;
        _syncLoopButtonUI(loopBtn);
    }
}

function _syncLoopButtonUI(btn) {
    if (!btn) return;
    const mode = Player.repeat || 'off';
    btn.classList.toggle('active', mode !== 'off');
    const icon = btn.querySelector('i');
    const span = btn.querySelector('span');
    if (icon) {
        icon.className = 'fas fa-repeat';
    }
    if (span) {
        if (mode === 'one') {
            span.textContent = '1';
        } else {
            span.textContent = '';
        }
    }
    btn.title = mode === 'off' ? 'Repeat: Off' : mode === 'all' ? 'Repeat: All' : 'Repeat: One';
}

function playSelectedPlaylist(shuffleStart = false) {
    const songs = State.playlists.songs || [];
    if (!songs.length) return;

    const queue = buildSelectedPlaylistPlaybackQueue?.() || [];
    if (!queue.length) return;

    const playlistId = State.playlists.selectedId;
    let startIndex = 0;

    // Explicitly set the mode so the two buttons are mutually exclusive
    setShuffleMode(shuffleStart);

    if (shuffleStart) {
        startIndex = Math.floor(Math.random() * queue.length);
    }

    if (setPlaybackQueue('playlist', queue, startIndex, playlistId)) {
        playFromCurrentQueue(startIndex);
    }
}

function setShuffleMode(enabled) {
    Player.shuffle = enabled;
    Player.saveSettings?.();
    Player.updateShuffleButton?.();
    Player.updateNowPlayingButtons?.();
    const btn = document.getElementById('playlistShuffleBtn');
    if (btn) btn.classList.toggle('active', enabled);
}

function playPlaylistSong(songId) {
    const songs = State.playlists.songs || [];
    const idx = songs.findIndex(s => s.id === songId);
    if (idx === -1) return;

    const queue = buildSelectedPlaylistPlaybackQueue?.() || [];
    const playlistId = State.playlists.selectedId;

    if (setPlaybackQueue('playlist', queue, idx, playlistId)) {
        playFromCurrentQueue(idx);
    }

    renderPlaylistDetailSongs(songs, true);
}

function togglePlaylistLoop() {
    const modes = ['off', 'all', 'one'];
    const currentIndex = modes.indexOf(Player.repeat);
    Player.repeat = modes[(currentIndex + 1) % modes.length];
    Player.saveSettings?.();
    Player.updateRepeatButton?.();
    Player.updateNowPlayingButtons?.();
    _syncLoopButtonUI(document.getElementById('playlistLoopBtn'));
}

// Close add songs modal compat (old system)
function closeAddSongsToSelectedPlaylistModal() { closeAddSongsModal(); }
function closeAddSongsToPlaylistModalOnOverlay(event) {
    if (event.target === event.currentTarget) closeAddSongsModal();
}
