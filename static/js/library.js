/**
 * Zora - Library Module
 * Library grid management, search, lazy loading, and song cards
 * 
 * Dependencies: api.js, ui.js, player.js, app.js (State, openConfirmAction, normalizeSearchText)
 *               playlists.js (openAddToPlaylistModal, loadPlaylists, loadSelectedPlaylistSongs, updatePlaylistPlaybackControls)
 *               playback.js (prunePlaybackQueueAfterDelete)
 */

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

function hasLibrarySearchQuery() {
    return normalizeSearchText(State.library.searchQuery).length > 0;
}

function getFilteredLibraryDownloads() {
    const query = normalizeSearchText(State.library.searchQuery);
    if (!query) return State.downloads;

    return State.downloads.filter((download) => {
        const title = download?.title || '';
        const artist = download?.artist || download?.uploader || '';
        const searchable = normalizeSearchText(`${title} ${artist}`);
        return searchable.includes(query);
    });
}

function applyLibraryViewMode() {
    const grid = document.getElementById('libraryGrid');
    const icon = document.getElementById('libraryViewIcon');
    const isList = State.library.viewMode === 'list';
    if (!grid) return;

    grid.classList.toggle('library-grid--list', isList);
    if (icon) {
        icon.className = isList ? 'fas fa-list' : 'fas fa-table-cells-large';
    }
}

function setLibraryViewMode(mode, options = {}) {
    const persist = options.persist !== false;
    State.library.viewMode = mode === 'list' ? 'list' : 'grid';
    applyLibraryViewMode();

    if (persist) {
        localStorage.setItem('library_view_mode', State.library.viewMode);
        // Sync to server (debounced)
        if (typeof syncPreferencesToServer === 'function') {
            syncPreferencesToServer('library_view_mode', State.library.viewMode);
        }
    }
}

function toggleLibraryView() {
    const nextMode = State.library.viewMode === 'list' ? 'grid' : 'list';
    closeAllLibraryActionMenus();
    setLibraryViewMode(nextMode);
}

function filterLibrary(query) {
    State.library.searchQuery = String(query || '');
    closeAllLibraryActionMenus();
    updateLibrary();
}

function loadMoreLibrarySongs() {
    if (hasLibrarySearchQuery()) return;
    if (State.library.visibleCount >= State.downloads.length) return;

    State.library.visibleCount = Math.min(
        State.library.visibleCount + State.library.batchSize,
        State.downloads.length
    );
    updateLibrary();
}

function maybeLoadMoreLibraryByScroll() {
    if (!isLibraryViewVisible()) return;
    if (hasLibrarySearchQuery()) return;
    if (State.library.visibleCount >= State.downloads.length) return;

    const mainContent = document.getElementById('mainContent');
    if (!mainContent) return;

    const remaining = mainContent.scrollHeight - (mainContent.scrollTop + mainContent.clientHeight);
    if (remaining <= 240) {
        loadMoreLibrarySongs();
    }
}

function closeAllLibraryActionMenus() {
    const openMenus = document.querySelectorAll('.library-card__menu.is-open');
    if (!openMenus.length) return;

    openMenus.forEach((menu) => {
        menu.classList.remove('is-open');
        const toggleBtn = menu.parentElement?.querySelector('.library-card__menu-toggle');
        if (toggleBtn) {
            toggleBtn.setAttribute('aria-expanded', 'false');
        }
    });
}

function toggleLibraryCardMenu(event) {
    event?.preventDefault();
    event?.stopPropagation();

    const toggleBtn = event?.currentTarget;
    const menuWrap = toggleBtn?.closest('.library-card__menu-wrap');
    const menu = menuWrap?.querySelector('.library-card__menu');
    if (!toggleBtn || !menu) return;

    const shouldOpen = !menu.classList.contains('is-open');
    closeAllLibraryActionMenus();

    if (shouldOpen) {
        menu.classList.add('is-open');
        toggleBtn.setAttribute('aria-expanded', 'true');
    } else {
        toggleBtn.setAttribute('aria-expanded', 'false');
    }
}

function openAddToPlaylistFromLibraryMenu(event, downloadId) {
    closeAllLibraryActionMenus();
    openAddToPlaylistModal(event, downloadId);
}

function createLibraryCardMarkup(download) {
    const filename = download.filename || '';
    const title = download.title || 'Unknown Title';
    const artist = download.artist || download.uploader || 'Unknown Artist';
    const thumbnail = download.thumbnail || '';
    const downloadId = Number(download.id);
    const canManage = Number.isFinite(downloadId) && downloadId > 0;

    if (!filename) return '';

    const actionsMenu = canManage ? `
        <div class="library-card__menu-wrap">
            <button class="library-card__menu-toggle"
                    title="Song actions"
                    aria-label="Song actions"
                    aria-haspopup="true"
                    aria-expanded="false"
                    onclick="toggleLibraryCardMenu(event)">
                <i class="fas fa-ellipsis-vertical"></i>
            </button>
            <div class="library-card__menu" role="menu">
                <button class="library-card__menu-item"
                        role="menuitem"
                        onclick="openAddToPlaylistFromLibraryMenu(event, ${downloadId})">
                    <i class="fas fa-plus"></i>
                    <span>Add to playlist</span>
                </button>
                <button class="library-card__menu-item library-card__menu-item--danger"
                        role="menuitem"
                        onclick="deleteLibraryTrack(event, ${downloadId})">
                    <i class="fas fa-trash"></i>
                    <span>Delete song</span>
                </button>
            </div>
        </div>
    ` : '';

    return `
        <div class="library-card library-item"
             data-title="${UI.escapeHtml(title)}"
             data-artist="${UI.escapeHtml(artist)}"
             onclick="playTrack('${UI.escapeJs(filename)}', '${UI.escapeJs(title)}', '${UI.escapeJs(artist)}', '${UI.escapeJs(thumbnail)}')">
            ${actionsMenu}
            <img src="${thumbnail}" alt="" class="library-card__thumb" onerror="this.src='/static/images/default-album.png'">
            <div class="library-card__info">
                <div class="library-card__title" title="${UI.escapeHtml(title)}">${UI.escapeHtml(title)}</div>
                <div class="library-card__artist" title="${UI.escapeHtml(artist)}">${UI.escapeHtml(artist)}</div>
            </div>
        </div>
    `;
}

async function deleteLibraryTrack(event, downloadId) {
    event?.preventDefault();
    event?.stopPropagation();
    closeAllLibraryActionMenus();

    const id = Number(downloadId);
    if (!Number.isFinite(id) || id <= 0) {
        UI.toast('Invalid song id', 'error');
        return;
    }

    const track = State.downloads.find(d => Number(d.id) === id);
    const displayName = track?.title || 'this song';

    const confirmed = await openConfirmAction({
        title: 'Delete Song From Library',
        message: `Delete "${displayName}" from your library and remove the audio file from storage? This action cannot be undone.`,
        confirmLabel: 'Delete Song',
        danger: true
    });
    if (!confirmed) return;

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

function updateLibraryLazyStatus(filteredCount = State.downloads.length, searchActive = false) {
    const status = document.getElementById('libraryLoadStatus');
    const trigger = document.getElementById('libraryLoadTrigger');
    if (!status || !trigger) return;

    if (State.downloads.length === 0) {
        status.classList.add('hidden');
        trigger.classList.add('hidden');
        return;
    }

    if (searchActive) {
        status.classList.remove('hidden');
        status.textContent = `${filteredCount} result${filteredCount !== 1 ? 's' : ''} in your library`;
        trigger.classList.add('hidden');
        return;
    }

    const hasMore = State.library.visibleCount < filteredCount;
    status.classList.remove('hidden');
    status.textContent = hasMore
        ? `Showing ${State.library.visibleCount} of ${filteredCount} songs. Scroll down to load more.`
        : `Showing all ${filteredCount} songs.`;
    trigger.classList.toggle('hidden', !hasMore);
}

function updateLibrary() {
    const grid = document.getElementById('libraryGrid');
    const count = document.getElementById('libraryCount');
    if (!grid) return;

    const filteredDownloads = getFilteredLibraryDownloads();
    const searchActive = hasLibrarySearchQuery();
    const totalCount = State.downloads.length;
    const filteredCount = filteredDownloads.length;

    if (count) {
        if (searchActive) {
            count.textContent = `${filteredCount} result${filteredCount !== 1 ? 's' : ''} / ${totalCount} song${totalCount !== 1 ? 's' : ''}`;
        } else {
            count.textContent = `${totalCount} song${totalCount !== 1 ? 's' : ''}`;
        }
    }

    applyLibraryViewMode();

    if (totalCount === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-music"></i>
                <h3>No songs yet</h3>
                <p>Downloaded songs will appear here</p>
            </div>
        `;
        updateLibraryLazyStatus(0, searchActive);
        return;
    }

    if (searchActive && filteredCount === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-search"></i>
                <h3>No matches found</h3>
                <p>Try a different song title or artist name.</p>
            </div>
        `;
        updateLibraryLazyStatus(0, true);
        return;
    }

    const visibleItems = searchActive
        ? filteredDownloads
        : filteredDownloads.slice(0, State.library.visibleCount);
    grid.innerHTML = visibleItems.map(createLibraryCardMarkup).join('');
    updateLibraryLazyStatus(filteredCount, searchActive);

    // If the current viewport is already at the bottom area, pull the next batch.
    if (!searchActive) {
        requestAnimationFrame(maybeLoadMoreLibraryByScroll);
    }
}
