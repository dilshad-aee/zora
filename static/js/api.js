/**
 * Zora - API Client Module
 * Handles all API communication with the backend
 */

const API = {
    /**
     * Fetch video/playlist information
     */
    async getInfo(url) {
        const response = await fetch('/api/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to fetch info');
        return data;
    },

    /**
     * Search YouTube
     */
    async search(query) {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Search failed');
        return data.results;
    },

    /**
     * Start download
     */
    async startDownload(url, format, quality, force = false) {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, format, quality, force })
        });

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
        const response = await fetch(`/api/status/${jobId}`);
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
        const response = await fetch('/api/history');
        return response.json();
    },

    /**
     * Clear history
     */
    async clearHistory() {
        await fetch('/api/history/clear', { method: 'POST' });
    },

    /**
     * Delete one song from history and filesystem
     */
    async deleteHistoryItem(downloadId) {
        const response = await fetch(`/api/history/delete/${downloadId}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to delete song');
        return data;
    },

    /**
     * List user playlists
     */
    async getPlaylists() {
        const response = await fetch('/api/playlists');
        return response.json();
    },

    /**
     * Create a playlist
     */
    async createPlaylist(name) {
        const response = await fetch('/api/playlists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to create playlist');
        return data;
    },

    /**
     * Delete a playlist
     */
    async deletePlaylist(playlistId) {
        const response = await fetch(`/api/playlists/${playlistId}`, { method: 'DELETE' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to delete playlist');
        return data;
    },

    /**
     * Get songs in a playlist
     */
    async getPlaylistSongs(playlistId) {
        const response = await fetch(`/api/playlists/${playlistId}/songs`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to load playlist songs');
        return data;
    },

    /**
     * Add a downloaded song to playlist
     */
    async addSongToPlaylist(playlistId, downloadId) {
        const response = await fetch(`/api/playlists/${playlistId}/songs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ download_id: downloadId })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to add song');
        return data;
    },

    /**
     * Remove a song from playlist
     */
    async removeSongFromPlaylist(playlistId, downloadId) {
        const response = await fetch(`/api/playlists/${playlistId}/songs/${downloadId}`, { method: 'DELETE' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to remove song');
        return data;
    },

    /**
     * Get settings
     */
    async getSettings() {
        const response = await fetch('/api/settings');
        return response.json();
    },

    /**
     * Save settings
     */
    async saveSettings(settings) {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });

        if (!response.ok) throw new Error('Failed to save settings');
        return response.json();
    }
};

// Export for module use
if (typeof module !== 'undefined') {
    module.exports = API;
}
