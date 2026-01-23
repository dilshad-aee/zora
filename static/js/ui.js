/**
 * Zora - UI Helpers Module
 * Common UI utilities, formatters, and DOM helpers
 */

const UI = {
    /**
     * Show an element by ID
     */
    show(id) {
        const el = document.getElementById(id);
        if (el) el.classList.remove('hidden');
    },

    /**
     * Hide an element by ID
     */
    hide(id) {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    },

    /**
     * Toggle element visibility
     */
    toggle(id, show) {
        if (show) {
            this.show(id);
        } else {
            this.hide(id);
        }
    },

    /**
     * Set element property
     */
    setElement(id, prop, value) {
        const el = document.getElementById(id);
        if (el) {
            if (prop === 'textContent' || prop === 'innerHTML') {
                el[prop] = value;
            } else if (prop === 'src' || prop === 'value') {
                el[prop] = value;
            } else {
                el.setAttribute(prop, value);
            }
        }
    },

    /**
     * Show toast notification
     */
    toast(message, type = 'success') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type === 'error' ? 'toast--error' : ''}`;
        toast.textContent = message;

        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3500);
    },

    /**
     * Format seconds to MM:SS or HH:MM:SS
     */
    formatTime(seconds) {
        if (!seconds || isNaN(seconds)) return '0:00';

        seconds = Math.floor(seconds);
        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;

        if (hrs > 0) {
            return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    },

    /**
     * Format number to human readable (1K, 1M, etc)
     */
    formatNumber(num) {
        if (!num) return '0';
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
        return num.toString();
    },

    /**
     * Format bytes to human readable
     */
    formatBytes(bytes) {
        if (!bytes) return '-- MB';
        if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB';
        if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
        if (bytes >= 1024) return (bytes / 1024).toFixed(0) + ' KB';
        return bytes + ' B';
    },

    /**
     * Format speed (bytes/sec)
     */
    formatSpeed(bytesPerSec) {
        if (!bytesPerSec) return '-- MB/s';
        if (bytesPerSec >= 1048576) return (bytesPerSec / 1048576).toFixed(1) + ' MB/s';
        if (bytesPerSec >= 1024) return (bytesPerSec / 1024).toFixed(0) + ' KB/s';
        return bytesPerSec + ' B/s';
    },

    /**
     * Escape HTML special characters
     */
    escapeHtml(str) {
        if (!str) return '';
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    },

    /**
     * Escape for JavaScript strings
     */
    escapeJs(str) {
        if (!str) return '';
        return str
            .replace(/\\/g, '\\\\')
            .replace(/'/g, "\\'")
            .replace(/"/g, '\\"');
    },

    /**
     * Create element with attributes
     */
    createElement(tag, attrs = {}, content = '') {
        const el = document.createElement(tag);

        for (const [key, value] of Object.entries(attrs)) {
            if (key === 'class') {
                el.className = value;
            } else if (key === 'onclick') {
                el.onclick = value;
            } else {
                el.setAttribute(key, value);
            }
        }

        if (content) {
            el.innerHTML = content;
        }

        return el;
    },

    /**
     * Render template with data
     */
    template(html, data) {
        return html.replace(/\{\{(\w+)\}\}/g, (match, key) => {
            return data[key] !== undefined ? data[key] : match;
        });
    },

    /**
     * Show loading overlay
     */
    showLoader(message = 'Loading...') {
        const overlay = document.getElementById('loaderOverlay');
        const text = document.getElementById('loaderText');
        if (overlay) {
            overlay.classList.remove('hidden');
            if (text && message) {
                text.textContent = message;
            }
        }
    },

    /**
     * Hide loading overlay
     */
    hideLoader() {
        const overlay = document.getElementById('loaderOverlay');
        if (overlay) {
            overlay.classList.add('hidden');
        }
    }
};

// Export for module use
if (typeof module !== 'undefined') {
    module.exports = UI;
}
