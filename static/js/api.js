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
        return response.json();
    },

    /**
     * Add to queue
     */
    async addToQueue(url, title, thumbnail, format, quality) {
        const response = await fetch('/api/queue/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, title, thumbnail, format, quality })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to add to queue');
        return data;
    },

    /**
     * Get queue
     */
    async getQueue() {
        const response = await fetch('/api/queue');
        return response.json();
    },

    /**
     * Remove from queue
     */
    async removeFromQueue(itemId) {
        await fetch(`/api/queue/remove/${itemId}`, { method: 'POST' });
    },

    /**
     * Clear queue
     */
    async clearQueue() {
        await fetch('/api/queue/clear', { method: 'POST' });
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
    },

    /**
     * Open downloads folder
     */
    async openFolder() {
        await fetch('/api/open-folder', { method: 'POST' });
    }
};

// Export for module use
if (typeof module !== 'undefined') {
    module.exports = API;
}
