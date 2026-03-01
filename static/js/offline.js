/**
 * Zora - Offline Manager Module
 * PWA offline caching for playlists — true offline listening
 *
 * Uses IndexedDB to store playlist metadata and the Cache API (via service worker)
 * to store audio files + thumbnails so they survive without network.
 *
 * Dependencies: api.js, ui.js, app.js (State)
 */

const OfflineManager = {
    DB_NAME: 'zora-offline-meta',
    DB_VERSION: 1,
    STORE: 'playlists',

    // In-memory cache of offline playlist IDs for fast badge checks
    _offlineIds: new Set(),
    _dbReady: null,

    // Active download state
    _activeDownload: null,

    // ─── IndexedDB ──────────────────────────────────────────────────────────

    _openDB() {
        if (this._dbReady) return this._dbReady;

        this._dbReady = new Promise((resolve, reject) => {
            const req = indexedDB.open(this.DB_NAME, this.DB_VERSION);
            req.onupgradeneeded = () => {
                const db = req.result;
                if (!db.objectStoreNames.contains(this.STORE)) {
                    db.createObjectStore(this.STORE, { keyPath: 'playlistId' });
                }
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
        return this._dbReady;
    },

    async _tx(mode) {
        const db = await this._openDB();
        return db.transaction(this.STORE, mode).objectStore(this.STORE);
    },

    async saveMeta(playlistId, data) {
        const store = await this._tx('readwrite');
        return new Promise((resolve, reject) => {
            const req = store.put({ playlistId, ...data, savedAt: Date.now() });
            req.onsuccess = () => {
                this._offlineIds.add(playlistId);
                resolve();
            };
            req.onerror = () => reject(req.error);
        });
    },

    async getMeta(playlistId) {
        const store = await this._tx('readonly');
        return new Promise((resolve, reject) => {
            const req = store.get(playlistId);
            req.onsuccess = () => resolve(req.result || null);
            req.onerror = () => reject(req.error);
        });
    },

    async getAllMeta() {
        const store = await this._tx('readonly');
        return new Promise((resolve, reject) => {
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result || []);
            req.onerror = () => reject(req.error);
        });
    },

    async deleteMeta(playlistId) {
        const store = await this._tx('readwrite');
        return new Promise((resolve, reject) => {
            const req = store.delete(playlistId);
            req.onsuccess = () => {
                this._offlineIds.delete(playlistId);
                resolve();
            };
            req.onerror = () => reject(req.error);
        });
    },

    // ─── Init ───────────────────────────────────────────────────────────────

    async init() {
        try {
            const all = await this.getAllMeta();
            this._offlineIds = new Set(all.map(m => m.playlistId));
        } catch { /* IndexedDB unavailable */ }
    },

    // ─── Status ─────────────────────────────────────────────────────────────

    isPlaylistOffline(playlistId) {
        return this._offlineIds.has(playlistId);
    },

    isDownloading() {
        return !!this._activeDownload;
    },

    // ─── Download Playlist for Offline ──────────────────────────────────────

    async downloadPlaylist(playlistId, playlistName, songs) {
        if (this._activeDownload) {
            UI.toast('An offline download is already in progress', 'error');
            return;
        }

        if (!songs || !songs.length) {
            UI.toast('No songs to save offline', 'error');
            return;
        }

        if (!navigator.serviceWorker || !navigator.serviceWorker.controller) {
            UI.toast('Service worker not ready — try refreshing', 'error');
            return;
        }

        this._activeDownload = {
            playlistId,
            total: songs.length,
            completed: 0,
            failed: 0,
            cancelled: false,
        };

        this._showProgressUI(playlistName, songs.length);

        const urlsToCache = [];

        for (let i = 0; i < songs.length; i++) {
            if (this._activeDownload.cancelled) break;

            const song = songs[i];
            const audioUrl = `/play/${encodeURIComponent(song.filename)}`;
            urlsToCache.push(audioUrl);

            // Also cache thumbnail
            if (song.thumbnail && song.thumbnail.startsWith('/api/thumbnails/')) {
                urlsToCache.push(song.thumbnail);
            }

            try {
                // Cache audio via direct fetch into the offline cache
                const cache = await caches.open('zora-offline');
                const cacheKey = new Request(new URL(audioUrl, location.origin).pathname);
                const existing = await cache.match(cacheKey);
                if (!existing) {
                    const response = await fetch(audioUrl);
                    if (response.ok) {
                        await cache.put(cacheKey, response);
                    } else {
                        this._activeDownload.failed++;
                    }
                }

                // Cache thumbnail
                if (song.thumbnail && song.thumbnail.startsWith('/api/thumbnails/')) {
                    const thumbKey = new Request(new URL(song.thumbnail, location.origin).pathname);
                    const thumbExisting = await cache.match(thumbKey);
                    if (!thumbExisting) {
                        const thumbResp = await fetch(song.thumbnail);
                        if (thumbResp.ok) await cache.put(thumbKey, thumbResp);
                    }
                }

                this._activeDownload.completed++;
            } catch {
                this._activeDownload.failed++;
            }

            this._updateProgressUI(this._activeDownload.completed + this._activeDownload.failed, songs.length);
        }

        if (this._activeDownload.cancelled) {
            // Clean up partial download
            this._removeProgressUI();
            this._activeDownload = null;
            return;
        }

        // Save metadata to IndexedDB
        await this.saveMeta(playlistId, {
            name: playlistName,
            songCount: songs.length,
            songs: songs.map(s => ({
                id: s.id,
                filename: s.filename,
                title: s.title,
                artist: s.artist || s.uploader || 'Unknown',
                thumbnail: s.thumbnail || '',
                duration: s.duration || 0,
            })),
            urls: urlsToCache,
        });

        const failed = this._activeDownload.failed;
        this._activeDownload = null;
        this._removeProgressUI();

        if (failed > 0) {
            UI.toast(`Saved offline with ${failed} failed track${failed > 1 ? 's' : ''}`, 'warning');
        } else {
            UI.toast(`"${playlistName}" saved for offline listening`, 'success');
        }

        // Refresh the detail header to show the updated offline button
        if (typeof _refreshOfflineButton === 'function') {
            _refreshOfflineButton(playlistId);
        }
    },

    // ─── Remove Offline Playlist ────────────────────────────────────────────

    async removePlaylist(playlistId) {
        const meta = await this.getMeta(playlistId);
        if (!meta) return;

        // Remove cached audio + thumbnail URLs
        if (meta.urls && meta.urls.length) {
            try {
                const cache = await caches.open('zora-offline');
                for (const url of meta.urls) {
                    const cacheKey = new Request(new URL(url, location.origin).pathname);
                    await cache.delete(cacheKey);
                }
            } catch { /* swallow */ }
        }

        await this.deleteMeta(playlistId);
        UI.toast('Offline data removed', 'success');
    },

    cancelDownload() {
        if (this._activeDownload) {
            this._activeDownload.cancelled = true;
        }
    },

    // ─── Storage Estimate ───────────────────────────────────────────────────

    async getStorageEstimate() {
        if (navigator.storage && navigator.storage.estimate) {
            const est = await navigator.storage.estimate();
            return {
                usage: est.usage || 0,
                quota: est.quota || 0,
                percent: est.quota ? Math.round((est.usage / est.quota) * 100) : 0,
            };
        }
        return null;
    },

    // ─── Progress UI ────────────────────────────────────────────────────────

    _showProgressUI(name, total) {
        // Remove any existing
        this._removeProgressUI();

        const bar = document.createElement('div');
        bar.id = 'offlineProgressBar';
        bar.className = 'offline-progress';
        bar.innerHTML = `
            <div class="offline-progress__inner">
                <div class="offline-progress__info">
                    <i class="fas fa-download"></i>
                    <span class="offline-progress__text">Saving "${UI.escapeHtml(name)}" for offline…</span>
                    <span class="offline-progress__count">0 / ${total}</span>
                </div>
                <div class="offline-progress__bar">
                    <div class="offline-progress__fill" style="width: 0%"></div>
                </div>
                <button class="offline-progress__cancel" onclick="OfflineManager.cancelDownload()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        document.body.appendChild(bar);
        requestAnimationFrame(() => bar.classList.add('offline-progress--visible'));
    },

    _updateProgressUI(done, total) {
        const bar = document.getElementById('offlineProgressBar');
        if (!bar) return;
        const pct = Math.round((done / total) * 100);
        const fill = bar.querySelector('.offline-progress__fill');
        const count = bar.querySelector('.offline-progress__count');
        if (fill) fill.style.width = `${pct}%`;
        if (count) count.textContent = `${done} / ${total}`;
    },

    _removeProgressUI() {
        const bar = document.getElementById('offlineProgressBar');
        if (bar) {
            bar.classList.remove('offline-progress--visible');
            setTimeout(() => bar.remove(), 300);
        }
    },
};

// ─── Global helpers for playlist UI integration ─────────────────────────────

async function savePlaylistOffline() {
    const playlistId = State.playlists.selectedId;
    const songs = State.playlists.songs || [];
    const playlist = (State.playlists.list || []).find(p => p.id === playlistId);
    const name = playlist?.name || 'Playlist';

    if (!playlistId || !songs.length) {
        UI.toast('Open a playlist with songs first', 'error');
        return;
    }

    await OfflineManager.downloadPlaylist(playlistId, name, songs);
}

async function removePlaylistOffline() {
    const playlistId = State.playlists.selectedId;
    if (!playlistId) return;

    await OfflineManager.removePlaylist(playlistId);
    _refreshOfflineButton(playlistId);
}

function _refreshOfflineButton(playlistId) {
    const container = document.getElementById('offlineBtnContainer');
    if (!container) return;

    if (OfflineManager.isPlaylistOffline(playlistId)) {
        container.innerHTML = `
            <button class="btn btn--small offline-btn offline-btn--saved" onclick="removePlaylistOffline()">
                <i class="fas fa-check-circle"></i> <span class="btn-text">Saved Offline</span>
            </button>`;
    } else {
        container.innerHTML = `
            <button class="btn btn--small offline-btn" onclick="savePlaylistOffline()">
                <i class="fas fa-cloud-arrow-down"></i> <span class="btn-text">Save Offline</span>
            </button>`;
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    OfflineManager.init();
});
