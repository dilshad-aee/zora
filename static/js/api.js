/**
 * Zora - API Client Module
 * Handles all API communication with the backend
 */

const API = {
    /**
     * Shared fetch wrapper with global 401/403 handling.
     * All API calls should go through this.
     */
    async _fetch(url, options = {}) {
        const response = await fetch(url, options);

        if (response.status === 401) {
            // Only redirect if user was previously logged in (session expired)
            if (State.user) {
                State.user = null;
                UI.toast('Session expired. Please log in again.', 'error');
                showView('login');
            }
            throw new Error('Session expired. Please log in again.');
        }

        if (response.status === 403) {
            UI.toast('You do not have permission to perform this action', 'error');
            throw new Error('Forbidden');
        }

        return response;
    },

    /**
     * Shared helper for JSON POST/PATCH/DELETE requests.
     */
    _jsonOptions(method, body) {
        return {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        };
    },

    // ==================== Auth ====================
    auth: {
        async login(email, password) {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Login failed');
            return data;
        },

        async signup(name, email, password, confirm_password) {
            const response = await fetch('/api/auth/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email, password, confirm_password })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Signup failed');
            return data;
        },

        async logout() {
            const response = await fetch('/api/auth/logout', { method: 'POST' });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Logout failed');
            return data;
        },

        async me() {
            const response = await fetch('/api/auth/me');
            if (!response.ok) return null;
            return response.json();
        },

        async changePassword(current_password, new_password) {
            const response = await API._fetch('/api/auth/password/change',
                API._jsonOptions('POST', { current_password, new_password })
            );
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Password change failed');
            return data;
        },

        async requestPasswordReset(email) {
            const response = await fetch('/api/auth/password/reset/request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Request failed');
            return data;
        },

        async confirmPasswordReset(token, new_password) {
            const response = await fetch('/api/auth/password/reset/confirm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, new_password })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Reset failed');
            return data;
        },

        async updateProfile(data) {
            const response = await API._fetch('/api/auth/profile',
                API._jsonOptions('PATCH', data)
            );
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Update failed');
            return result;
        }
    },

    /**
     * Fetch video/playlist information
     */
    async getInfo(url) {
        const response = await this._fetch('/api/info',
            this._jsonOptions('POST', { url })
        );

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to fetch info');
        return data;
    },

    /**
     * Search YouTube
     */
    async search(query) {
        const response = await this._fetch('/api/search',
            this._jsonOptions('POST', { query })
        );

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Search failed');
        return data.results;
    },

    /**
     * Start download
     */
    async startDownload(url, format, quality, force = false) {
        const response = await this._fetch('/api/download',
            this._jsonOptions('POST', { url, format, quality, force })
        );

        const data = await response.json();

        // Handle duplicate response
        if (response.status === 409 && data.is_duplicate) {
            return { isDuplicate: true, ...data };
        }

        if (!response.ok) throw new Error(data.error || 'Download failed');
        return data;
    },

    /**
     * Get download status
     */
    async getStatus(jobId) {
        const response = await this._fetch(`/api/status/${jobId}`);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || `Status request failed (${response.status})`);
        }
        return data;
    },

    /**
     * Get download history
     */
    async getHistory() {
        const response = await this._fetch('/api/history');
        return response.json();
    },

    /**
     * Clear history
     */
    async clearHistory() {
        await this._fetch('/api/history/clear', { method: 'POST' });
    },

    /**
     * Delete one song from history and filesystem
     */
    async deleteHistoryItem(downloadId) {
        const response = await this._fetch(`/api/history/delete/${downloadId}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to delete song');
        return data;
    },

    /**
     * List user playlists
     */
    async getPlaylists() {
        const response = await this._fetch('/api/playlists');
        return response.json();
    },

    /**
     * Create a playlist
     */
    async createPlaylist(options) {
        const body = typeof options === 'string' ? { name: options } : options;
        const response = await this._fetch('/api/playlists',
            this._jsonOptions('POST', body)
        );

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to create playlist');
        return data;
    },

    /**
     * Update a playlist
     */
    async updatePlaylist(playlistId, updates) {
        const response = await this._fetch(`/api/playlists/${playlistId}`,
            this._jsonOptions('PATCH', updates)
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to update playlist');
        return data;
    },

    /**
     * Explore public playlists
     */
    async explorePlaylists(params = {}) {
        const qs = new URLSearchParams();
        if (params.category) qs.set('category', params.category);
        if (params.sort) qs.set('sort', params.sort);
        if (params.q) qs.set('q', params.q);
        if (params.page) qs.set('page', params.page);
        const url = `/api/playlists/explore${qs.toString() ? '?' + qs.toString() : ''}`;
        const response = await this._fetch(url);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to load explore');
        return data;
    },

    /**
     * Like a playlist
     */
    async likePlaylist(playlistId) {
        const response = await this._fetch(`/api/playlists/${playlistId}/like`,
            { method: 'POST' }
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to like playlist');
        return data;
    },

    /**
     * Unlike a playlist
     */
    async unlikePlaylist(playlistId) {
        const response = await this._fetch(`/api/playlists/${playlistId}/like`,
            { method: 'DELETE' }
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to unlike playlist');
        return data;
    },

    /**
     * Delete a playlist
     */
    async deletePlaylist(playlistId) {
        const response = await this._fetch(`/api/playlists/${playlistId}`, { method: 'DELETE' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to delete playlist');
        return data;
    },

    /**
     * Get songs in a playlist
     */
    async getPlaylistSongs(playlistId) {
        const response = await this._fetch(`/api/playlists/${playlistId}/songs`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to load playlist songs');
        return data;
    },

    /**
     * Add a downloaded song to playlist
     */
    async addSongToPlaylist(playlistId, downloadId) {
        const response = await this._fetch(`/api/playlists/${playlistId}/songs`,
            this._jsonOptions('POST', { download_id: downloadId })
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to add song');
        return data;
    },

    /**
     * Remove a song from playlist
     */
    async removeSongFromPlaylist(playlistId, downloadId) {
        const response = await this._fetch(`/api/playlists/${playlistId}/songs/${downloadId}`, { method: 'DELETE' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to remove song');
        return data;
    },

    /**
     * Get settings
     */
    async getSettings() {
        const response = await this._fetch('/api/settings');
        return response.json();
    },

    /**
     * Save settings
     */
    async saveSettings(settings) {
        const response = await this._fetch('/api/settings',
            this._jsonOptions('POST', settings)
        );

        if (!response.ok) throw new Error('Failed to save settings');
        return response.json();
    },

    // ==================== Preferences ====================
    preferences: {
        async get() {
            const response = await API._fetch('/api/preferences');
            if (!response.ok) return {};
            return response.json();
        },

        async save(prefs) {
            const response = await API._fetch('/api/preferences',
                API._jsonOptions('PUT', prefs)
            );
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to save preferences');
            return data;
        }
    },

    // ==================== Admin ====================
    admin: {
        async getUsers(page = 1, perPage = 20, search = '') {
            let url = `/api/admin/users?page=${page}&per_page=${perPage}`;
            if (search) url += `&search=${encodeURIComponent(search)}`;
            const response = await API._fetch(url);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to fetch users');
            return data;
        },

        async updateUser(userId, updates) {
            const response = await API._fetch(`/api/admin/users/${userId}`,
                API._jsonOptions('PATCH', updates)
            );
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to update user');
            return data;
        },

        async getAuditLogs(page = 1, perPage = 30, action = '') {
            let url = `/api/admin/audit-logs?page=${page}&per_page=${perPage}`;
            if (action) url += `&action=${encodeURIComponent(action)}`;
            const response = await API._fetch(url);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to fetch audit logs');
            return data;
        },

        async getServerStatus() {
            const response = await API._fetch('/api/admin/server-status');
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to fetch server status');
            return data;
        }
    },

    // ==================== Categories ====================
    categories: {
        async list() {
            const response = await API._fetch('/api/categories');
            if (!response.ok) return [];
            return response.json();
        },

        async create(data) {
            const response = await API._fetch('/api/admin/categories',
                API._jsonOptions('POST', data)
            );
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Failed to create category');
            return result;
        },

        async update(id, data) {
            const response = await API._fetch(`/api/admin/categories/${id}`,
                API._jsonOptions('PATCH', data)
            );
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Failed to update category');
            return result;
        },

        async delete(id) {
            const response = await API._fetch(`/api/admin/categories/${id}`,
                { method: 'DELETE' }
            );
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Failed to delete category');
            return result;
        }
    }
};

// Export for module use
if (typeof module !== 'undefined') {
    module.exports = API;
}
