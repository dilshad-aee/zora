/**
 * Zora - Audio Player Module
 * Clean, Mobile-Friendly Audio Player
 * 
 * @version 4.0.0
 * @author Zora Team
 */

const Player = {
    // Core elements
    audio: null,
    progressBar: null,
    progressFill: null,

    // State
    currentTrack: null,
    isLoading: false,
    isReady: false,
    isDragging: false,
    isInitialized: false,

    // Features
    playbackRate: 1.0,
    sleepTimer: null,
    sleepTimerEnd: null,
    savedPositions: {},

    /**
     * Initialize the player
     */
    init() {
        if (this.isInitialized) return;

        this.audio = document.getElementById('audioPlayer');
        this.progressBar = document.getElementById('playerProgressBar');
        this.progressFill = document.getElementById('playerProgress');

        if (!this.audio) {
            console.warn('Audio element not found');
            return;
        }

        this.isInitialized = true;

        // Load saved data
        this.loadSavedPositions();
        this.loadSavedVolume();

        // Setup all event listeners
        this.setupAudioEvents();
        this.setupControlButtons();
        this.setupProgressBar();
        this.setupVolumeControl();
        this.setupKeyboardShortcuts();
        this.setupMediaSession();

        console.log('🎵 Zora Player v4.0.0 initialized');
    },

    /**
     * Setup control button event listeners
     */
    setupControlButtons() {
        // Play/Pause button
        const playBtn = document.getElementById('playPauseBtn');
        if (playBtn) {
            if (playBtn) {
                playBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.toggle();
                });
            }
        }

        // Skip backward button
        const skipBackBtn = document.getElementById('btnSkipBack');
        if (skipBackBtn) {
            skipBackBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.skipBackward(10);
            });
        }

        // Skip forward button
        const skipFwdBtn = document.getElementById('btnSkipForward');
        if (skipFwdBtn) {
            skipFwdBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.skipForward(10);
            });
        }

        // Mute button
        const muteBtn = document.getElementById('btnMute');
        if (muteBtn) {
            muteBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggleMute();
            });
        }

        // Speed button
        const speedBtn = document.getElementById('btnSpeed');
        if (speedBtn) {
            speedBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.cyclePlaybackRate();
            });
        }

        // Sleep timer button
        const sleepBtn = document.getElementById('btnSleepTimer');
        if (sleepBtn) {
            sleepBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (typeof showSleepTimerMenu === 'function') {
                    showSleepTimerMenu();
                }
            });
        }
    },

    /**
     * Setup volume slider
     */
    setupVolumeControl() {
        const slider = document.getElementById('volumeSlider');
        if (slider) {
            slider.addEventListener('input', (e) => {
                this.setVolume(e.target.value / 100);
            });
            slider.addEventListener('change', (e) => {
                this.setVolume(e.target.value / 100);
            });
        }
    },

    /**
     * Setup audio element events
     */
    setupAudioEvents() {
        // Playback state changes
        this.audio.addEventListener('play', () => {
            this.updatePlayButton(true);
            this.updateMediaSession();
        });

        this.audio.addEventListener('pause', () => {
            this.updatePlayButton(false);
            this.saveCurrentPosition();
        });

        this.audio.addEventListener('ended', () => {
            this.onTrackEnded();
        });

        // Time updates
        this.audio.addEventListener('timeupdate', () => {
            if (!this.isDragging) {
                this.updateProgressBar();
                this.updateTimeDisplay();
            }
            this.checkSleepTimer();
        });

        this.audio.addEventListener('loadedmetadata', () => {
            this.updateDurationDisplay();
            this.isReady = true;
            this.restorePosition();
        });

        // Loading states
        this.audio.addEventListener('waiting', () => this.setLoading(true));
        this.audio.addEventListener('canplay', () => this.setLoading(false));
        this.audio.addEventListener('canplaythrough', () => this.setLoading(false));

        // Error handling
        this.audio.addEventListener('error', (e) => this.handleError(e));

        // Volume changes
        this.audio.addEventListener('volumechange', () => {
            this.updateVolumeIcon();
            this.saveVolume();
        });
    },

    /**
     * Setup progress bar with mouse and touch support
     */
    setupProgressBar() {
        if (!this.progressBar) return;

        // Click to seek
        this.progressBar.addEventListener('click', (e) => {
            e.stopPropagation();
            this.seekToPosition(e);
        });

        // Mouse drag
        this.progressBar.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            this.startDrag(e);
        });

        // Touch drag
        this.progressBar.addEventListener('touchstart', (e) => {
            e.stopPropagation();
            this.startDrag(e);
        }, { passive: true });

        // Document level events for drag
        document.addEventListener('mousemove', (e) => {
            if (this.isDragging) {
                this.onDrag(e);
            }
        });

        document.addEventListener('mouseup', () => {
            if (this.isDragging) {
                this.endDrag();
            }
        });

        document.addEventListener('touchmove', (e) => {
            if (this.isDragging) {
                this.onDrag(e);
            }
        }, { passive: true });

        document.addEventListener('touchend', () => {
            if (this.isDragging) {
                this.endDrag();
            }
        });
    },

    /**
     * Start dragging progress bar
     */
    startDrag(e) {
        if (!this.audio || !this.audio.duration) return;
        this.isDragging = true;
        this.progressBar.classList.add('dragging');
        this.seekToPosition(e);
    },

    /**
     * Handle drag movement
     */
    onDrag(e) {
        if (!this.isDragging) return;
        this.seekToPosition(e);
    },

    /**
     * End dragging
     */
    endDrag() {
        this.isDragging = false;
        if (this.progressBar) {
            this.progressBar.classList.remove('dragging');
        }
    },

    /**
     * Seek to position based on event
     */
    seekToPosition(e) {
        if (!this.audio || !this.audio.duration || !this.progressBar) return;

        const rect = this.progressBar.getBoundingClientRect();
        let clientX;

        if (e.touches && e.touches.length > 0) {
            clientX = e.touches[0].clientX;
        } else if (e.changedTouches && e.changedTouches.length > 0) {
            clientX = e.changedTouches[0].clientX;
        } else {
            clientX = e.clientX;
        }

        const percent = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const newTime = percent * this.audio.duration;

        this.audio.currentTime = newTime;
        this.updateProgressBar();
        this.updateTimeDisplay();
    },

    /**
     * Setup keyboard shortcuts
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Don't trigger in input fields
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            if (!this.audio) return;

            switch (e.code) {
                case 'Space':
                    e.preventDefault();
                    this.toggle();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    this.skipBackward(e.shiftKey ? 30 : 10);
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    this.skipForward(e.shiftKey ? 30 : 10);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this.adjustVolume(0.1);
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    this.adjustVolume(-0.1);
                    break;
                case 'KeyM':
                    this.toggleMute();
                    break;
            }
        });
    },

    /**
     * Setup Media Session API for lock screen controls
     */
    setupMediaSession() {
        if (!('mediaSession' in navigator)) return;

        navigator.mediaSession.setActionHandler('play', () => this.resume());
        navigator.mediaSession.setActionHandler('pause', () => this.pause());
        navigator.mediaSession.setActionHandler('stop', () => this.stop());
        navigator.mediaSession.setActionHandler('seekbackward', () => this.skipBackward(10));
        navigator.mediaSession.setActionHandler('seekforward', () => this.skipForward(10));

        navigator.mediaSession.setActionHandler('previoustrack', () => {
            if (typeof Playlist !== 'undefined' && Playlist.playPrevious) {
                Playlist.playPrevious();
            }
        });

        navigator.mediaSession.setActionHandler('nexttrack', () => {
            if (typeof Playlist !== 'undefined' && Playlist.playNext) {
                Playlist.playNext();
            }
        });

        try {
            navigator.mediaSession.setActionHandler('seekto', (details) => {
                if (details.seekTime !== undefined && this.audio) {
                    this.audio.currentTime = details.seekTime;
                }
            });
        } catch (e) {
            // Seek not supported
        }
    },

    /**
     * Update Media Session metadata
     */
    updateMediaSession() {
        if (!('mediaSession' in navigator) || !this.currentTrack) return;

        navigator.mediaSession.metadata = new MediaMetadata({
            title: this.currentTrack.title || 'Unknown Title',
            artist: this.currentTrack.artist || 'Unknown Artist',
            album: this.currentTrack.album || '',
            artwork: [
                {
                    src: this.currentTrack.thumbnail || '/static/images/default-album.png',
                    sizes: '512x512',
                    type: 'image/png'
                }
            ]
        });

        if (this.audio && !isNaN(this.audio.duration)) {
            try {
                navigator.mediaSession.setPositionState({
                    duration: this.audio.duration,
                    playbackRate: this.playbackRate,
                    position: this.audio.currentTime
                });
            } catch (e) {
                // Position state not supported
            }
        }
    },

    // ==================== PLAYBACK CONTROLS ====================

    /**
     * Play a track
     */
    play(filename, title, artist, thumbnail, album = '') {
        if (!filename || !this.audio) {
            console.warn('Cannot play: missing filename or audio element');
            return;
        }

        // Save current position before switching
        this.saveCurrentPosition();

        // Reset state
        this.isReady = false;
        this.setLoading(true);
        this.audio.pause();

        // Set new source
        this.audio.src = `/play/${encodeURIComponent(filename)}`;
        this.currentTrack = { filename, title, artist, thumbnail, album };

        // Apply playback rate
        this.audio.playbackRate = this.playbackRate;

        // Update UI
        this.updateTrackInfo(title, artist, thumbnail);
        this.showPlayer();

        // Load and play
        this.audio.load();

        const playPromise = this.audio.play();
        if (playPromise !== undefined) {
            playPromise
                .then(() => {
                    console.log('▶️ Playing:', title || filename);
                    this.setLoading(false);
                })
                .catch((error) => {
                    if (error.name !== 'AbortError' && error.name !== 'NotAllowedError') {
                        console.error('Playback error:', error);
                        this.showToast('Error playing audio', 'error');
                    }
                    this.setLoading(false);
                });
        }
    },

    /**
     * Toggle play/pause
     */
    toggle() {
        if (!this.audio || !this.audio.src) return;

        if (this.audio.paused) {
            this.audio.play().then(() => {
                this.updatePlayButton(true);
            }).catch(e => {
                if (e.name !== 'AbortError') {
                    console.error('Play error:', e);
                    this.showToast('Playback failed', 'error');
                }
            });
            // Optimistic update
            this.updatePlayButton(true);
        } else {
            this.audio.pause();
            this.updatePlayButton(false);
            this.showToast('Paused', 'info');
        }
    },

    /**
     * Pause playback
     */
    pause() {
        if (this.audio) {
            this.audio.pause();
        }
    },

    /**
     * Resume playback
     */
    resume() {
        if (this.audio && this.audio.src) {
            this.audio.play().catch(e => console.log('Resume interrupted'));
        }
    },

    /**
     * Stop playback
     */
    stop() {
        if (!this.audio) return;
        this.saveCurrentPosition();
        this.audio.pause();
        this.audio.currentTime = 0;
        this.updatePlayButton(false);
        this.currentTrack = null;
        this.clearSleepTimer();
    },

    /**
     * Skip forward
     */
    skipForward(seconds = 10) {
        if (!this.audio || isNaN(this.audio.duration)) return;
        this.audio.currentTime = Math.min(this.audio.duration - 0.1, this.audio.currentTime + seconds);
        this.showSkipIndicator(`+${seconds}s`);
    },

    /**
     * Skip backward
     */
    skipBackward(seconds = 10) {
        if (!this.audio) return;
        this.audio.currentTime = Math.max(0, this.audio.currentTime - seconds);
        this.showSkipIndicator(`-${seconds}s`);
    },

    /**
     * Seek to specific time
     */
    seek(event) {
        // This is called from onclick on progress bar
        event.stopPropagation();
        this.seekToPosition(event);
    },

    // ==================== VOLUME CONTROLS ====================

    /**
     * Set volume (0-1)
     */
    setVolume(value) {
        if (!this.audio) return;
        this.audio.volume = Math.max(0, Math.min(1, value));

        const slider = document.getElementById('volumeSlider');
        if (slider) {
            slider.value = this.audio.volume * 100;
        }
    },

    /**
     * Adjust volume by delta
     */
    adjustVolume(delta) {
        if (!this.audio) return;
        this.setVolume(this.audio.volume + delta);
        this.showToast(`Volume: ${Math.round(this.audio.volume * 100)}%`, 'info');
    },

    /**
     * Get current volume
     */
    getVolume() {
        return this.audio ? this.audio.volume : 1;
    },

    /**
     * Toggle mute
     */
    toggleMute() {
        if (!this.audio) return;
        this.audio.muted = !this.audio.muted;
        this.updateVolumeIcon();
    },

    /**
     * Update volume icon
     */
    updateVolumeIcon() {
        const icon = document.getElementById('volumeIcon');
        if (!icon || !this.audio) return;

        if (this.audio.muted || this.audio.volume === 0) {
            icon.className = 'fas fa-volume-mute';
        } else if (this.audio.volume < 0.5) {
            icon.className = 'fas fa-volume-down';
        } else {
            icon.className = 'fas fa-volume-up';
        }
    },

    /**
     * Save volume to localStorage
     */
    saveVolume() {
        if (this.audio) {
            try {
                localStorage.setItem('zora_volume', this.audio.volume.toString());
            } catch (e) { }
        }
    },

    /**
     * Load saved volume
     */
    loadSavedVolume() {
        try {
            const saved = localStorage.getItem('zora_volume');
            if (saved !== null && this.audio) {
                this.audio.volume = parseFloat(saved);
                const slider = document.getElementById('volumeSlider');
                if (slider) {
                    slider.value = this.audio.volume * 100;
                }
            }
        } catch (e) { }
    },

    // ==================== PLAYBACK SPEED ====================

    /**
     * Set playback rate
     */
    setPlaybackRate(rate) {
        if (!this.audio) return;
        this.playbackRate = Math.max(0.25, Math.min(3.0, rate));
        this.audio.playbackRate = this.playbackRate;

        const speedEl = document.getElementById('playbackSpeed');
        if (speedEl) {
            speedEl.textContent = `${this.playbackRate}x`;
        }

        this.showToast(`Speed: ${this.playbackRate}x`, 'info');
    },

    /**
     * Cycle through playback rates
     */
    cyclePlaybackRate() {
        const rates = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];
        const currentIndex = rates.indexOf(this.playbackRate);
        const nextIndex = currentIndex === -1 ? 2 : (currentIndex + 1) % rates.length;
        this.setPlaybackRate(rates[nextIndex]);
    },

    // ==================== SLEEP TIMER ====================

    /**
     * Set sleep timer
     */
    setSleepTimer(minutes) {
        this.clearSleepTimer();

        if (minutes <= 0) {
            this.showToast('Sleep timer cancelled', 'info');
            this.updateSleepTimerDisplay(0);
            return;
        }

        this.sleepTimerEnd = Date.now() + (minutes * 60 * 1000);
        this.sleepTimer = setTimeout(() => {
            this.pause();
            this.showToast('Sleep timer ended', 'info');
            this.sleepTimerEnd = null;
            this.updateSleepTimerDisplay(0);
        }, minutes * 60 * 1000);

        this.showToast(`Sleep timer: ${minutes} minutes`, 'info');
    },

    /**
     * Clear sleep timer
     */
    clearSleepTimer() {
        if (this.sleepTimer) {
            clearTimeout(this.sleepTimer);
            this.sleepTimer = null;
            this.sleepTimerEnd = null;
        }
    },

    /**
     * Check and update sleep timer
     */
    checkSleepTimer() {
        if (this.sleepTimerEnd) {
            const remaining = Math.max(0, this.sleepTimerEnd - Date.now());
            this.updateSleepTimerDisplay(remaining);
        }
    },

    /**
     * Update sleep timer display
     */
    updateSleepTimerDisplay(remaining) {
        const display = document.getElementById('sleepTimerDisplay');
        if (!display) return;

        if (remaining > 0) {
            const mins = Math.ceil(remaining / 60000);
            display.textContent = `${mins}m`;
            display.style.display = 'inline';
        } else {
            display.style.display = 'none';
        }
    },

    // ==================== UI UPDATES ====================

    /**
     * Update play/pause button
     */
    updatePlayButton(isPlaying) {
        const btn = document.getElementById('playPauseBtn');
        if (!btn) return;

        // Force icon update
        const icon = btn.querySelector('i');
        if (icon) {
            icon.className = isPlaying ? 'fas fa-pause' : 'fas fa-play';
        } else {
            // Fallback if icon is missing
            btn.innerHTML = isPlaying
                ? '<i class="fas fa-pause"></i>'
                : '<i class="fas fa-play"></i>';
        }

        btn.setAttribute('aria-label', isPlaying ? 'Pause' : 'Play');

        if (isPlaying) {
            btn.classList.add('is-playing');
        } else {
            btn.classList.remove('is-playing');
        }
    },

    /**
     * Update progress bar
     */
    updateProgressBar() {
        if (!this.audio || !this.progressFill || isNaN(this.audio.duration)) return;
        const percent = (this.audio.currentTime / this.audio.duration) * 100;
        this.progressFill.style.width = `${percent}%`;

        // Update handle position
        const handle = document.getElementById('playerHandle');
        if (handle) {
            handle.style.left = `${percent}%`;
        }
    },

    /**
     * Update time display
     */
    updateTimeDisplay() {
        if (!this.audio) return;

        const timeEl = document.getElementById('playerTime');
        if (timeEl) {
            timeEl.textContent = this.formatTime(this.audio.currentTime);
        }

        const remainingEl = document.getElementById('playerRemaining');
        if (remainingEl && !isNaN(this.audio.duration)) {
            const remaining = this.audio.duration - this.audio.currentTime;
            remainingEl.textContent = `-${this.formatTime(remaining)}`;
        }
    },

    /**
     * Update duration display
     */
    updateDurationDisplay() {
        const durationEl = document.getElementById('playerDuration');
        if (durationEl && this.audio && !isNaN(this.audio.duration)) {
            durationEl.textContent = this.formatTime(this.audio.duration);
        }
    },

    /**
     * Update track info display
     */
    updateTrackInfo(title, artist, thumbnail) {
        const defaultThumb = '/static/images/default-album.png';

        const thumbEl = document.getElementById('playerThumb');
        const titleEl = document.getElementById('playerTitle');
        const artistEl = document.getElementById('playerArtist');

        if (thumbEl) thumbEl.src = thumbnail || defaultThumb;
        if (titleEl) titleEl.textContent = title || 'Unknown Title';
        if (artistEl) artistEl.textContent = artist || 'Unknown Artist';

        // Update page title
        if (title) {
            document.title = `${title} - Zora`;
        }
    },

    /**
     * Show player bar
     */
    showPlayer() {
        const playerBar = document.getElementById('playerBar');
        if (playerBar) {
            playerBar.classList.remove('hidden');
        }
    },

    /**
     * Set loading state
     */
    setLoading(loading) {
        this.isLoading = loading;

        const loader = document.getElementById('playerLoading');
        if (loader) {
            loader.style.display = loading ? 'flex' : 'none';
        }

        const playBtn = document.getElementById('playPauseBtn');
        if (playBtn) {
            if (loading) {
                playBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            } else {
                this.updatePlayButton(!this.audio?.paused);
            }
        }
    },

    /**
     * Show skip indicator
     */
    showSkipIndicator(text) {
        let indicator = document.getElementById('skipIndicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'skipIndicator';
            indicator.className = 'skip-indicator';
            document.body.appendChild(indicator);
        }
        indicator.textContent = text;
        indicator.classList.add('show');
        setTimeout(() => indicator.classList.remove('show'), 600);
    },

    /**
     * Show toast notification
     */
    showToast(message, type = 'info') {
        if (typeof UI !== 'undefined' && UI.toast) {
            UI.toast(message, type);
            return;
        }

        let container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        }, 2500);
    },

    // ==================== POSITION SAVING ====================

    /**
     * Save current position
     */
    saveCurrentPosition() {
        if (!this.currentTrack || !this.audio || isNaN(this.audio.currentTime)) return;

        const key = this.currentTrack.filename;
        if (this.audio.currentTime > 10 && this.audio.currentTime < this.audio.duration - 10) {
            this.savedPositions[key] = {
                time: this.audio.currentTime,
                timestamp: Date.now()
            };
            this.persistPositions();
        }
    },

    /**
     * Restore saved position
     */
    restorePosition() {
        if (!this.currentTrack || !this.audio) return;

        const saved = this.savedPositions[this.currentTrack.filename];
        if (saved && Date.now() - saved.timestamp < 7 * 24 * 60 * 60 * 1000) {
            this.audio.currentTime = saved.time;
            this.showToast('Resuming playback', 'info');
        }
    },

    /**
     * Clear saved position
     */
    clearSavedPosition() {
        if (this.currentTrack) {
            delete this.savedPositions[this.currentTrack.filename];
            this.persistPositions();
        }
    },

    /**
     * Load positions from localStorage
     */
    loadSavedPositions() {
        try {
            const saved = localStorage.getItem('zora_positions');
            if (saved) {
                this.savedPositions = JSON.parse(saved);
            }
        } catch (e) { }
    },

    /**
     * Persist positions to localStorage
     */
    persistPositions() {
        try {
            localStorage.setItem('zora_positions', JSON.stringify(this.savedPositions));
        } catch (e) { }
    },

    // ==================== EVENT HANDLERS ====================

    /**
     * Handle track ended
     */
    onTrackEnded() {
        this.updatePlayButton(false);
        this.clearSavedPosition();

        if (this.progressFill) {
            this.progressFill.style.width = '0%';
        }

        if (typeof Playlist !== 'undefined' && Playlist.playNext) {
            Playlist.playNext();
        }
    },

    /**
     * Handle audio errors
     */
    handleError(e) {
        this.setLoading(false);
        this.updatePlayButton(false);

        const error = this.audio?.error;
        let message = 'Error loading audio';

        if (error) {
            const messages = {
                1: 'Audio loading aborted',
                2: 'Network error',
                3: 'Audio decoding failed',
                4: 'Audio format not supported'
            };
            message = messages[error.code] || message;
        }

        console.error('Audio error:', message);
        this.showToast(message, 'error');
    },

    // ==================== UTILITIES ====================

    /**
     * Format time as MM:SS or HH:MM:SS
     */
    formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return '0:00';

        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hrs > 0) {
            return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    },

    /**
     * Get current track
     */
    getCurrentTrack() {
        return this.currentTrack;
    },

    /**
     * Check if playing
     */
    isPlaying() {
        return this.audio ? !this.audio.paused : false;
    },

    /**
     * Get current time
     */
    getCurrentTime() {
        return this.audio ? this.audio.currentTime : 0;
    },

    /**
     * Get duration
     */
    getDuration() {
        return this.audio && !isNaN(this.audio.duration) ? this.audio.duration : 0;
    },

    /**
     * Get progress percentage
     */
    getProgress() {
        if (!this.audio || !this.audio.duration || isNaN(this.audio.duration)) return 0;
        return (this.audio.currentTime / this.audio.duration) * 100;
    }
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Player.init());
} else {
    Player.init();
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Player;
}
