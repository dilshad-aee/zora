/**
 * Zora - Audio Player Module
 * Handles audio playback, progress, and controls
 */

const Player = {
    audio: null,
    currentTrack: null,

    /**
     * Initialize the player
     */
    init() {
        this.audio = document.getElementById('audioPlayer');

        if (this.audio) {
            this.audio.addEventListener('play', () => this.updateButton(true));
            this.audio.addEventListener('pause', () => this.updateButton(false));
            this.audio.addEventListener('ended', () => this.updateButton(false));
            this.audio.addEventListener('timeupdate', () => this.updateProgress());
            this.audio.addEventListener('loadedmetadata', () => this.updateDuration());
        }
    },

    /**
     * Play a track
     */
    play(filename, title, artist, thumbnail) {
        if (!filename || !this.audio) return;

        this.audio.src = `/play/${encodeURIComponent(filename)}`;
        this.currentTrack = { filename, title, artist, thumbnail };

        // Update UI
        UI.setElement('playerThumb', 'src', thumbnail || '');
        UI.setElement('playerTitle', 'textContent', title || 'Unknown');
        UI.setElement('playerArtist', 'textContent', artist || 'Unknown');

        // Show player bar
        UI.show('playerBar');

        // Start playback
        this.audio.play().catch(e => {
            console.error('Playback error:', e);
            UI.toast('Error playing audio', 'error');
        });
    },

    /**
     * Toggle play/pause
     */
    toggle() {
        if (!this.audio) return;

        if (this.audio.paused) {
            this.audio.play();
        } else {
            this.audio.pause();
        }
    },

    /**
     * Update play/pause button icon
     */
    updateButton(isPlaying) {
        const btn = document.getElementById('playPauseBtn');
        if (btn) {
            btn.innerHTML = isPlaying
                ? '<i class="fas fa-pause"></i>'
                : '<i class="fas fa-play"></i>';
        }
    },

    /**
     * Update progress bar and time display
     */
    updateProgress() {
        if (!this.audio || !this.audio.duration) return;

        const percent = (this.audio.currentTime / this.audio.duration) * 100;
        const progress = document.getElementById('playerProgress');
        if (progress) {
            progress.style.width = `${percent}%`;
        }

        const timeEl = document.getElementById('playerTime');
        if (timeEl) {
            timeEl.textContent = UI.formatTime(this.audio.currentTime);
        }
    },

    /**
     * Update duration display
     */
    updateDuration() {
        const durationEl = document.getElementById('playerDuration');
        if (durationEl && this.audio) {
            durationEl.textContent = UI.formatTime(this.audio.duration);
        }
    },

    /**
     * Seek to position
     */
    seek(event) {
        if (!this.audio || !this.audio.duration) return;

        const bar = document.getElementById('playerProgressBar');
        if (!bar) return;

        const rect = bar.getBoundingClientRect();
        const percent = (event.clientX - rect.left) / rect.width;
        this.audio.currentTime = percent * this.audio.duration;
    },

    /**
     * Toggle mute
     */
    toggleMute() {
        if (!this.audio) return;

        this.audio.muted = !this.audio.muted;
        const icon = document.getElementById('volumeIcon');
        if (icon) {
            icon.className = this.audio.muted ? 'fas fa-volume-mute' : 'fas fa-volume-up';
        }
    },

    /**
     * Get current track info
     */
    getCurrentTrack() {
        return this.currentTrack;
    }
};

// Export for module use
if (typeof module !== 'undefined') {
    module.exports = Player;
}
