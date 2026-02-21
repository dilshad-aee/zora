/**
 * Zora - Audio Player Module
 * Handles audio playback, progress, and controls
 * 
 * @version 2.0.0
 * @author Zora Team
 */

const Player = {
    audio: null,
    currentTrack: null,
    isLoading: false,
    isReady: false,
    isInitialized: false,

    // Playback resume
    _lastSavedPosition: 0,
    _playbackSaveTimer: null,

    // Playback modes
    shuffle: false,
    repeat: 'off', // 'off', 'all', 'one'

    // Sleep timer
    sleepTimer: null,
    sleepTimerEnd: null,
    sleepTimerInterval: null,
    _sleepOutsideClickTimeout: null,
    _sleepOutsideClickHandler: null,

    // Volume
    savedVolume: 1,

    /**
     * Initialize the player
     */
    init() {
        if (this.isInitialized) return;

        this.audio = document.getElementById('audioPlayer');

        if (!this.audio) {
            console.warn('Audio element not found');
            return;
        }

        // Add background play support
        this.setupBackgroundPlay();

        // Add haptic feedback support
        this.setupHapticFeedback();

        // Add gesture controls
        this.setupGestureControls();

        this.isInitialized = true;

        // Load saved settings
        this.loadSettings();

        // Setup control buttons
        this.setupControls();

        // Playback events
        this.audio.addEventListener('play', () => {
            this.updateButton(true);
            this.updateNowPlayingButtons();
        });

        this.audio.addEventListener('pause', () => {
            this.updateButton(false);
            this.updateNowPlayingButtons();
        });

        this.audio.addEventListener('ended', () => {
            this.onEnded();
        });

        // Progress events
        this.audio.addEventListener('timeupdate', () => {
            this.updateProgress();
            this.updateNowPlayingProgress();
            this.maybeSavePlaybackState();
        });

        // Save state on pause (user pauses or tabs away)
        this.audio.addEventListener('pause', () => {
            this.savePlaybackStateNow();
        });

        this.audio.addEventListener('loadedmetadata', () => {
            this.updateDuration();
            this.syncNowPlayingUI();
            this.isReady = true;
        });

        // Loading events
        this.audio.addEventListener('waiting', () => {
            this.setLoading(true);
        });

        this.audio.addEventListener('canplay', () => {
            this.setLoading(false);
        });

        this.audio.addEventListener('canplaythrough', () => {
            this.setLoading(false);
        });

        // Error handling
        this.audio.addEventListener('error', (e) => {
            this.onError(e);
        });

        // Save playback state before page unload
        window.addEventListener('beforeunload', () => {
            this.savePlaybackStateNow();
        });

        // Mark as initialized
        console.log('🎵 Player initialized');
    },

    /**
     * Setup background play support
     */
    setupBackgroundPlay() {
        // Lock screen controls (iOS Safari)
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.audio) {
                this.audio.play().catch(e => console.log('Background play error:', e));
            }
        });

        // Background play detection
        this.audio.addEventListener('pause', () => {
            if (document.hidden) {
                // App was backgrounded - try to resume
                setTimeout(() => {
                    if (document.hidden && this.audio && !this.audio.paused) {
                        this.audio.play().catch(e => console.log('Background resume error:', e));
                    }
                }, 1000);
            }
        });
    },

    /**
     * Setup haptic feedback support
     */
    setupHapticFeedback() {
        this.hapticEnabled = localStorage.getItem('player_haptic') === 'true';

        // Check for haptic support
        if (navigator.vibrate) {
            this.hasHapticSupport = true;
        }
    },

    /**
     * Trigger haptic feedback
     */
    triggerHaptic() {
        if (this.hapticEnabled && this.hasHapticSupport) {
            // Simple vibration pattern
            navigator.vibrate(50);
        }
    },

    /**
     * Setup gesture controls
     */
    setupGestureControls() {
        // Swipe gestures for mobile
        let touchStartX = 0;
        let touchStartY = 0;
        let touchStartTime = 0;

        document.addEventListener('touchstart', (e) => {
            if (e.target.closest('.player__progress-bar, .now-playing__progress-bar')) {
                // Progress bar seeking - handled separately
                return;
            }

            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchStartTime = Date.now();
        });

        document.addEventListener('touchend', (e) => {
            const touchEndX = e.changedTouches[0].clientX;
            const touchEndY = e.changedTouches[0].clientY;
            const touchEndTime = Date.now();

            const deltaX = touchEndX - touchStartX;
            const deltaY = touchEndY - touchStartY;
            const deltaTime = touchEndTime - touchStartTime;

            // Swipe detection
            if (Math.abs(deltaX) > 50 && Math.abs(deltaY) < 30 && deltaTime < 300) {
                if (deltaX > 0) {
                    // Swipe right - next track
                    this.triggerHaptic();
                    this.skipForward(10);
                } else {
                    // Swipe left - previous track
                    this.triggerHaptic();
                    this.skipBackward(10);
                }
            }

            // Tap detection
            if (Math.abs(deltaX) < 10 && Math.abs(deltaY) < 10 && deltaTime < 200) {
                // Simple tap - trigger haptic feedback
                this.triggerHaptic();
            }
        });

        // Double tap for play/pause
        let lastTapTime = 0;
        document.addEventListener('touchend', (e) => {
            const currentTime = Date.now();
            const deltaTime = currentTime - lastTapTime;

            if (deltaTime < 300) {
                // Double tap detected
                this.triggerHaptic();
                this.toggle();
                lastTapTime = 0; // Reset
            } else {
                lastTapTime = currentTime;
            }
        });

        // Long press for more options
        let longPressTimeout;
        document.addEventListener('touchstart', (e) => {
            if (e.target.closest('.player__btn')) {
                longPressTimeout = setTimeout(() => {
                    this.triggerHaptic();
                    // Show context menu (could be implemented)
                    console.log('Long press detected - show context menu');
                }, 500);
            }
        });

        document.addEventListener('touchend', () => {
            if (longPressTimeout) {
                clearTimeout(longPressTimeout);
                longPressTimeout = null;
            }
        });
    },

    /**
     * Play a track
     * @param {string} filename - Audio file name
     * @param {string} title - Track title
     * @param {string} artist - Artist name
     * @param {string} thumbnail - Thumbnail URL
     */
    play(filename, title, artist, thumbnail) {
        if (!filename) {
            console.warn('No filename provided');
            return;
        }

        if (!this.audio) {
            console.warn('Audio element not initialized');
            return;
        }

        // Reset state
        this.isReady = false;
        this.setLoading(true);

        // Stop current playback cleanly
        this.audio.pause();

        // Set new source
        this.audio.src = `/play/${encodeURIComponent(filename)}`;
        this.currentTrack = { filename, title, artist, thumbnail };

        // Update UI elements safely
        this.updatePlayerUI(title, artist, thumbnail);

        // Show player bar
        if (typeof UI !== 'undefined' && UI.show) {
            UI.show('playerBar');
        } else {
            const playerBar = document.getElementById('playerBar');
            if (playerBar) playerBar.style.display = 'block';
        }

        // Adjust main content padding after player shows
        if (typeof adjustMainPadding === 'function') {
            setTimeout(adjustMainPadding, 100);
        }

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
                    this.handlePlayError(error, title);
                });
        }
    },

    /**
     * Update player UI elements
     * @private
     */
    updatePlayerUI(title, artist, thumbnail) {
        const defaultThumb = '/static/images/default-album.png';

        const thumbEl = document.getElementById('playerThumb');
        const titleEl = document.getElementById('playerTitle');
        const artistEl = document.getElementById('playerArtist');

        if (thumbEl) {
            thumbEl.src = thumbnail || defaultThumb;
            thumbEl.onerror = function () {
                this.onerror = null;
                this.src = defaultThumb;
            };
        }
        if (titleEl) titleEl.textContent = title || 'Unknown Title';
        if (artistEl) artistEl.textContent = artist || 'Unknown Artist';
    },

    /**
     * Handle play errors intelligently
     * @private
     */
    handlePlayError(error, title) {
        this.setLoading(false);

        // Errors to ignore (not real playback failures)
        const ignoredErrors = ['AbortError', 'NotAllowedError'];

        if (ignoredErrors.includes(error.name)) {
            console.log(`ℹ️ Play interrupted (${error.name}):`, title || 'track');
            return;
        }

        // Real errors - show to user
        console.error('❌ Playback error:', error);

        const errorMessages = {
            'NotSupportedError': 'Audio format not supported',
            'NetworkError': 'Network error - check connection',
            'MediaError': 'Error loading audio file'
        };

        const message = errorMessages[error.name] || 'Error playing audio';

        if (typeof UI !== 'undefined' && UI.toast) {
            UI.toast(message, 'error');
        } else {
            alert(message);
        }
    },

    /**
     * Toggle play/pause
     */
    toggle() {
        if (!this.audio) return;

        if (this.audio.paused) {
            this.audio.play().catch((error) => {
                this.handlePlayError(error, this.currentTrack?.title);
            });
        } else {
            this.audio.pause();
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
            this.audio.play().catch((error) => {
                this.handlePlayError(error, this.currentTrack?.title);
            });
        }
    },

    /**
     * Stop playback and reset
     */
    stop() {
        if (!this.audio) return;

        this.audio.pause();
        this.audio.currentTime = 0;
        this.updateButton(false);
        this.currentTrack = null;
    },

    /**
     * Update play/pause button icon
     * @param {boolean} isPlaying - Current play state
     */
    updateButton(isPlaying) {
        const btn = document.getElementById('playPauseBtn');
        if (btn) {
            btn.innerHTML = isPlaying
                ? '<i class="fas fa-pause"></i>'
                : '<i class="fas fa-play"></i>';
            btn.setAttribute('aria-label', isPlaying ? 'Pause' : 'Play');
        }
    },

    /**
     * Update progress bar and time display
     */
    updateProgress() {
        if (!this.audio || !this.audio.duration || isNaN(this.audio.duration)) return;

        const percent = (this.audio.currentTime / this.audio.duration) * 100;

        const progress = document.getElementById('playerProgress');
        if (progress) {
            progress.style.width = `${percent}%`;
        }

        const timeEl = document.getElementById('playerTime');
        if (timeEl) {
            timeEl.textContent = this.formatTime(this.audio.currentTime);
        }
    },

    /**
     * Update duration display
     */
    updateDuration() {
        const durationEl = document.getElementById('playerDuration');
        if (durationEl && this.audio && !isNaN(this.audio.duration)) {
            durationEl.textContent = this.formatTime(this.audio.duration);
        }
    },

    /**
     * Format seconds to MM:SS
     * @param {number} seconds - Time in seconds
     * @returns {string} Formatted time string
     */
    formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return '0:00';

        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    },

    /**
     * Seek to position (supports mouse and touch)
     * @param {Event} event - Click or touch event
     */
    seek(event) {
        if (!this.audio || !this.audio.duration || isNaN(this.audio.duration)) return;

        const bar = document.getElementById('playerProgressBar');
        if (!bar) return;

        const rect = bar.getBoundingClientRect();

        // Support both mouse and touch events
        const clientX = event.touches
            ? event.touches[0].clientX
            : event.clientX;

        const percent = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        this.audio.currentTime = percent * this.audio.duration;
    },

    /**
     * Skip forward by seconds
     * @param {number} seconds - Seconds to skip (default: 10)
     */
    skipForward(seconds = 10) {
        if (!this.audio || isNaN(this.audio.duration)) return;
        const newTime = Math.min(this.audio.duration, this.audio.currentTime + seconds);
        this.audio.currentTime = newTime;
        this.showSkipFeedback('forward', seconds);
    },

    /**
     * Skip backward by seconds
     * @param {number} seconds - Seconds to skip (default: 10)
     */
    skipBackward(seconds = 10) {
        if (!this.audio) return;
        const newTime = Math.max(0, this.audio.currentTime - seconds);
        this.audio.currentTime = newTime;
        this.showSkipFeedback('backward', seconds);
    },

    /**
     * Show skip feedback
     * @param {string} direction - 'forward' or 'backward'
     * @param {number} seconds - Seconds skipped
     */
    showSkipFeedback(direction, seconds) {
        const existing = document.getElementById('skipFeedback');
        if (existing) existing.remove();

        const feedback = document.createElement('div');
        feedback.id = 'skipFeedback';
        feedback.className = 'skip-feedback skip-feedback--${direction}';
        feedback.innerHTML = `
            <div class="skip-feedback__content">
                <i class="fas fa-${direction === 'forward' ? 'forward' : 'backward'}"></i>
                <span class="skip-feedback__time">${seconds}s</span>
            </div>
        `;

        document.body.appendChild(feedback);

        // Smooth animation
        setTimeout(() => {
            feedback.classList.add('show');
        }, 50);

        // Auto-hide
        setTimeout(() => {
            feedback.classList.remove('show');
            setTimeout(() => feedback.remove(), 300);
        }, 1000);
    },

    /**
     * Set volume
     * @param {number} value - Volume level (0 to 1)
     */
    setVolume(value) {
        if (!this.audio) return;
        this.audio.volume = Math.max(0, Math.min(1, value));

        // Update volume icon
        this.updateVolumeIcon();

        // Sync all volume sliders
        this.syncVolumeSliders();

        // Save volume setting
        this.saveSettings();

        // Show smooth volume feedback
        this.showVolumeFeedback(value);
    },

    /**
     * Show smooth volume feedback
     * @param {number} volume - Volume level (0 to 1)
     */
    showVolumeFeedback(volume) {
        const existing = document.getElementById('volumeFeedback');
        if (existing) existing.remove();

        const feedback = document.createElement('div');
        feedback.id = 'volumeFeedback';
        feedback.className = 'volume-feedback';
        feedback.innerHTML = `
            <div class="volume-feedback__icon">
                <i class="fas fa-volume-${volume === 0 ? 'mute' : volume < 0.5 ? 'down' : 'up'}"></i>
            </div>
            <div class="volume-feedback__level">
                <div class="volume-feedback__bar" style="width: ${Math.round(volume * 100)}%"></div>
            </div>
        `;

        document.body.appendChild(feedback);

        // Position near volume control
        const volumeBtn = document.getElementById('btnMute');
        if (volumeBtn) {
            const rect = volumeBtn.getBoundingClientRect();
            feedback.style.left = rect.left + (rect.width / 2) - 40 + 'px';
            feedback.style.top = rect.top - 80 + 'px';
        }

        // Smooth animation
        setTimeout(() => {
            feedback.classList.add('show');
        }, 50);

        // Auto-hide
        setTimeout(() => {
            feedback.classList.remove('show');
            setTimeout(() => feedback.remove(), 300);
        }, 1500);
    },

    /**
     * Sync all volume sliders
     */
    syncVolumeSliders() {
        const volumePercent = Math.round((this.audio?.volume || 1) * 100);

        const sliders = [
            document.getElementById('volumeSlider'),
            document.getElementById('nowPlayingVolume')
        ];

        sliders.forEach(slider => {
            if (slider) slider.value = volumePercent;
        });
    },

    /**
     * Get current volume
     * @returns {number} Current volume (0 to 1)
     */
    getVolume() {
        return this.audio ? this.audio.volume : 1;
    },


    /**
     * Play next track in queue
     */
    playNext() {
        if (typeof window.playNextTrack === 'function') {
            window.playNextTrack();
        } else {
            console.warn('playNextTrack function not found');
        }
    },

    /**
     * Play previous track in queue
     */
    playPrevious() {
        if (typeof window.playPreviousTrack === 'function') {
            window.playPreviousTrack();
            return;
        }

        if (typeof window.playTrackAtIndex === 'function' && Number.isFinite(this.currentTrackIndex) && this.currentTrackIndex > 0) {
            window.playTrackAtIndex(this.currentTrackIndex - 1);
            return;
        }

        if (this.audio) {
            // Fallback: restart current track
            this.audio.currentTime = 0;
        }
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
     * Update volume icon based on state
     * @private
     */
    updateVolumeIcon() {
        const icon = document.getElementById('volumeIcon');
        if (!icon) return;

        if (this.audio.muted || this.audio.volume === 0) {
            icon.className = 'fas fa-volume-mute';
        } else if (this.audio.volume < 0.5) {
            icon.className = 'fas fa-volume-down';
        } else {
            icon.className = 'fas fa-volume-up';
        }
    },

    /**
     * Set loading state
     * @param {boolean} loading - Loading state
     */
    setLoading(loading) {
        this.isLoading = loading;

        const loader = document.getElementById('playerLoading');
        if (loader) {
            loader.style.display = loading ? 'block' : 'none';
        }

        const playBtn = document.getElementById('playPauseBtn');
        if (playBtn) {
            if (loading) {
                playBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            } else {
                this.updateButton(!this.audio?.paused);
            }
        }
    },

    /**
     * Handle track ended
     * @private
     */
    onEnded() {
        // Handle repeat modes
        if (this.repeat === 'one') {
            this.audio.currentTime = 0;
            this.audio.play().catch(e => console.log('Repeat play interrupted'));
            return;
        }

        this.updateButton(false);

        // Reset progress
        const progress = document.getElementById('playerProgress');
        if (progress) {
            progress.style.width = '0%';
        }

        // Play next track from library
        if (typeof window.playNextTrack === 'function') {
            window.playNextTrack();
        }
    },

    /**
     * Handle audio errors
     * @private
     */
    onError(e) {
        this.setLoading(false);
        this.updateButton(false);

        const error = this.audio?.error;
        let message = 'Error loading audio';

        if (error) {
            const errorCodes = {
                1: 'Audio loading aborted',
                2: 'Network error',
                3: 'Audio decoding failed',
                4: 'Audio format not supported'
            };
            message = errorCodes[error.code] || message;
        }

        console.error('❌ Audio error:', message, e);

        if (typeof UI !== 'undefined' && UI.toast) {
            UI.toast(message, 'error');
        }
    },

    /**
     * Get current track info
     * @returns {Object|null} Current track object
     */
    getCurrentTrack() {
        return this.currentTrack;
    },

    /**
     * Debounced save: saves playback state every 10+ seconds of playback progress.
     * Called on every timeupdate event.
     */
    maybeSavePlaybackState() {
        if (!this.audio || !this.currentTrack) return;

        const pos = this.audio.currentTime || 0;
        // Only save if position changed by at least 10 seconds
        if (Math.abs(pos - this._lastSavedPosition) < 10) return;
        this._lastSavedPosition = pos;

        this._queuePlaybackStateSave();
    },

    /**
     * Force-save playback state immediately (on pause, beforeunload).
     */
    savePlaybackStateNow() {
        if (!this.currentTrack) return;

        // Clear any pending debounce
        if (this._playbackSaveTimer) {
            clearTimeout(this._playbackSaveTimer);
            this._playbackSaveTimer = null;
        }

        const pos = this.audio ? this.audio.currentTime || 0 : 0;
        this._lastSavedPosition = pos;
        this._doSavePlaybackState();
    },

    /**
     * Debounce the save so we don't spam the server.
     */
    _queuePlaybackStateSave() {
        if (this._playbackSaveTimer) return; // Already queued
        this._playbackSaveTimer = setTimeout(() => {
            this._playbackSaveTimer = null;
            this._doSavePlaybackState();
        }, 3000);
    },

    /**
     * Actually save to localStorage + server.
     */
    _doSavePlaybackState() {
        const track = this.currentTrack;
        if (!track || !track.filename) return;

        const pos = this.audio ? this.audio.currentTime || 0 : 0;
        const state = {
            filename: track.filename,
            title: track.title || '',
            artist: track.artist || '',
            thumbnail: track.thumbnail || '',
            position: String(Math.floor(pos))
        };

        // Save to localStorage (instant, works offline)
        try {
            localStorage.setItem('last_playback_state', JSON.stringify(state));
        } catch (e) { /* quota exceeded, ignore */ }

        // Sync to server (debounced via syncPreferencesToServer)
        if (typeof syncPreferencesToServer === 'function') {
            syncPreferencesToServer('last_track_filename', state.filename);
            syncPreferencesToServer('last_track_title', state.title);
            syncPreferencesToServer('last_track_artist', state.artist);
            syncPreferencesToServer('last_track_thumbnail', state.thumbnail);
            syncPreferencesToServer('last_track_position', state.position);
        }
    },

    /**
     * Clear saved playback state (call when queue ends).
     */
    clearPlaybackState() {
        try {
            localStorage.removeItem('last_playback_state');
        } catch (e) { /* ignore */ }
        this._lastSavedPosition = 0;
    },

    /**
     * Check if audio is playing
     * @returns {boolean} Playing state
     */
    isPlaying() {
        return this.audio ? !this.audio.paused : false;
    },

    /**
     * Get current playback time
     * @returns {number} Current time in seconds
     */
    getCurrentTime() {
        return this.audio ? this.audio.currentTime : 0;
    },

    /**
     * Get total duration
     * @returns {number} Duration in seconds
     */
    getDuration() {
        return this.audio && !isNaN(this.audio.duration) ? this.audio.duration : 0;
    },

    /**
     * Get playback progress percentage
     * @returns {number} Progress (0 to 100)
     */
    getProgress() {
        if (!this.audio || !this.audio.duration || isNaN(this.audio.duration)) return 0;
        return (this.audio.currentTime / this.audio.duration) * 100;
    },

    /**
     * Toggle lyrics
     */
    toggleLyrics() {
        this.lyricsEnabled = !this.lyricsEnabled;
        this.updateLyricsDisplay();
        this.showToast(this.lyricsEnabled ? 'Lyrics on' : 'Lyrics off');

        // Show/hide lyrics panel
        const lyricsPanel = document.getElementById('lyricsPanel');
        if (lyricsPanel) {
            lyricsPanel.style.display = this.lyricsEnabled ? 'block' : 'none';
        }
    },

    /**
     * Update lyrics display
     */
    updateLyricsDisplay() {
        const btn = document.getElementById('btnLyrics');
        if (btn) {
            btn.classList.toggle('active', this.lyricsEnabled);
        }
    },

    /**
     * Load lyrics for current track
     */
    loadLyrics() {
        if (!this.currentTrack || !this.lyricsEnabled) return;

        // Simple lyrics loading (in production, would use API)
        const lyricsPanel = document.getElementById('lyricsPanel');
        if (lyricsPanel) {
            lyricsPanel.innerHTML = `
                <div class="lyrics-panel__header">
                    <h3>${this.currentTrack.title}</h3>
                    <span class="lyrics-panel__artist">${this.currentTrack.artist}</span>
                </div>
                <div class="lyrics-panel__content">
                    <p class="lyrics-panel__text">
                        <em>Lyrics loading...</em>
                    </p>
                </div>
            `;
        }
    },

    /**
     * Update equalizer display
     */
    updateEqualizerDisplay() {
        const btn = document.getElementById('btnEqualizer');
        if (btn) {
            btn.classList.toggle('active', this.equalizerEnabled);
        }
    },

    /**
     * Update playback speed display
     * @param {number} speed - Playback speed
     */
    updatePlaybackSpeedDisplay(speed) {
        const display = document.getElementById('playbackSpeed');
        if (display) {
            display.textContent = `${speed}x`;
        }
    },

    /**
     * Setup control button event listeners
     */
    setupControls() {
        const playBtn = document.getElementById('playPauseBtn');
        if (playBtn) {
            playBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggle();
            });
        }

        // Skip buttons
        document.getElementById('btnSkipBack')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.skipBackward(10);
        });

        document.getElementById('btnSkipForward')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.skipForward(10);
        });

        // Track navigation buttons  
        document.getElementById('btnPrevTrack')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.playPrevious();
        });

        document.getElementById('btnNextTrack')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.playNext();
        });

        // Mute button
        document.getElementById('btnMute')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleMute();
        });

        // Volume slider (desktop)
        const volumeSlider = document.getElementById('volumeSlider');
        if (volumeSlider) {
            volumeSlider.addEventListener('input', (e) => {
                this.setVolume(e.target.value / 100);
                e.target.style.setProperty('--slider-percent', `${e.target.value}%`);
            });
        }

        // Shuffle button
        document.getElementById('btnShuffle')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleShuffle();
        });

        // Repeat button
        document.getElementById('btnRepeat')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.cycleRepeat();
        });

        // Sleep timer button
        document.getElementById('btnSleepTimer')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.showSleepTimerMenu();
        });

        // Lyrics button
        document.getElementById('btnLyrics')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleLyrics();
        });

        // Now Playing panel toggle
        document.getElementById('btnMobileControls')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.openNowPlaying();
        });

        // Now Playing close button
        document.getElementById('btnCloseNowPlaying')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.closeNowPlaying();
        });

        // Now Playing controls
        document.getElementById('btnPlayPauseNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggle();
        });

        document.getElementById('btnSkipBackNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.skipBackward(10);
        });

        document.getElementById('btnSkipForwardNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.skipForward(10);
        });

        document.getElementById('btnPrevTrackNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.playPrevious();
        });

        document.getElementById('btnNextTrackNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.playNext();
        });

        document.getElementById('btnShuffleNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleShuffle();
        });

        document.getElementById('btnRepeatNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.cycleRepeat();
        });

        document.getElementById('btnEqualizerNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleEqualizer();
        });

        document.getElementById('btnLyricsNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleLyrics();
        });

        document.getElementById('btnSleepTimerNP')?.addEventListener('click', (e) => {
            e.preventDefault();
            // Use global showSleepTimerMenu which shows the modal
            if (typeof window.showSleepTimerMenu === 'function') {
                window.showSleepTimerMenu();
            } else {
                this.showSleepTimerMenu();
            }
        });

        // Now Playing volume
        const npVolume = document.getElementById('nowPlayingVolume');
        if (npVolume) {
            npVolume.addEventListener('input', (e) => {
                this.setVolume(e.target.value / 100);
                e.target.style.setProperty('--slider-percent', `${e.target.value}%`);
            });
        }

        // Now Playing progress bar
        const npProgressBar = document.getElementById('nowPlayingProgressBar');
        if (npProgressBar) {
            npProgressBar.addEventListener('click', (e) => this.seekFromNowPlaying(e));
            npProgressBar.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this.seekFromNowPlaying(e);
            }, { passive: false });
        }

        // Progress bar seeking
        const progressBar = document.getElementById('playerProgressBar');
        if (progressBar) {
            progressBar.addEventListener('click', (e) => this.seek(e));
            progressBar.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this.seek(e);
            }, { passive: false });
        }

        // Cast button
        document.getElementById('btnCast')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleCast();
        });

        // Offline mode button
        document.getElementById('btnOffline')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleOfflineMode();
        });

        // Accessibility button
        document.getElementById('btnAccessibility')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleAccessibilityMode();
        });

        // Theme button
        document.getElementById('btnTheme')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleTheme();
        });
    },

    /**
     * Load saved settings
     */
    loadSettings() {
        try {
            this.shuffle = localStorage.getItem('player_shuffle') === 'true';
            this.repeat = localStorage.getItem('player_repeat') || 'off';

            const savedVol = parseFloat(localStorage.getItem('player_volume'));
            this.savedVolume = Number.isFinite(savedVol) ? savedVol : 1;

            if (this.audio) {
                this.audio.volume = this.savedVolume;
            }

            // Sync volume sliders
            this.syncVolumeSliders();

            this.updateShuffleButton();
            this.updateRepeatButton();
            this.updateNowPlayingButtons();
        } catch (e) {
            console.warn('Could not load player settings');
        }
    },

    /**
     * Save settings
     */
    saveSettings() {
        try {
            localStorage.setItem('player_shuffle', String(this.shuffle));
            localStorage.setItem('player_repeat', this.repeat);
            const vol = this.audio ? this.audio.volume : 1;
            localStorage.setItem('player_volume', String(vol));

            // Sync to server (debounced)
            if (typeof syncPreferencesToServer === 'function') {
                syncPreferencesToServer('player_shuffle', String(this.shuffle));
                syncPreferencesToServer('player_repeat', this.repeat);
                syncPreferencesToServer('player_volume', String(vol));
            }
        } catch (e) {
            console.warn('Could not save player settings');
        }
    },

    /**
     * Toggle shuffle mode
     */
    toggleShuffle() {
        this.shuffle = !this.shuffle;
        this.updateShuffleButton();
        this.updateNowPlayingButtons();
        this.saveSettings();
        if (typeof window.updatePlaylistPlaybackControls === 'function') {
            window.updatePlaylistPlaybackControls();
        }
        this.showToast(this.shuffle ? 'Shuffle on' : 'Shuffle off');
    },

    /**
     * Update shuffle button UI
     */
    updateShuffleButton() {
        const btn = document.getElementById('btnShuffle');
        if (btn) {
            btn.classList.toggle('active', this.shuffle);
            const label = btn.querySelector('span');
            if (label) {
                label.textContent = this.shuffle ? 'Shuffle On' : 'Shuffle';
            }
        }
    },

    /**
     * Cycle through repeat modes
     */
    cycleRepeat() {
        const modes = ['off', 'all', 'one'];
        const currentIndex = modes.indexOf(this.repeat);
        this.repeat = modes[(currentIndex + 1) % modes.length];
        this.updateRepeatButton();
        this.updateNowPlayingButtons();
        this.saveSettings();
        if (typeof window.updatePlaylistPlaybackControls === 'function') {
            window.updatePlaylistPlaybackControls();
        }

        const messages = { off: 'Repeat off', all: 'Repeat all', one: 'Repeat one' };
        this.showToast(messages[this.repeat]);
    },

    /**
     * Update repeat button UI
     */
    updateRepeatButton() {
        const btn = document.getElementById('btnRepeat');
        if (!btn) return;

        btn.classList.remove('active', 'repeat-one');

        // Find or create the icon and label
        let icon = btn.querySelector('i');
        let label = btn.querySelector('span:not(.repeat-badge)');

        if (this.repeat === 'all') {
            btn.classList.add('active');
            if (icon) icon.className = 'fas fa-repeat';
            if (label) label.textContent = 'Repeat All';
        } else if (this.repeat === 'one') {
            btn.classList.add('active', 'repeat-one');
            if (icon) icon.className = 'fas fa-repeat';
            if (label) label.textContent = 'Repeat 1';
        } else {
            if (icon) icon.className = 'fas fa-repeat';
            if (label) label.textContent = 'Repeat';
        }
    },

    /**
     * Show sleep timer menu
     */
    showSleepTimerMenu() {
        const existing = document.getElementById('sleepTimerMenu');
        if (existing) {
            existing.remove();
            return;
        }

        const menu = document.createElement('div');
        menu.id = 'sleepTimerMenu';
        menu.className = 'sleep-timer-menu';
        menu.innerHTML = `
            <div class="sleep-timer-menu__content">
                <div class="sleep-timer-menu__header">
                    <span>Sleep Timer</span>
                    <button class="sleep-timer-menu__close" onclick="Player.closeSleepTimerMenu()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="sleep-timer-menu__options">
                    <button onclick="Player.setSleepTimer(5)">5 min</button>
                    <button onclick="Player.setSleepTimer(10)">10 min</button>
                    <button onclick="Player.setSleepTimer(15)">15 min</button>
                    <button onclick="Player.setSleepTimer(30)">30 min</button>
                    <button onclick="Player.setSleepTimer(45)">45 min</button>
                    <button onclick="Player.setSleepTimer(60)">1 hour</button>
                    ${this.sleepTimer ? '<button class="cancel" onclick="Player.cancelSleepTimer()">Cancel Timer</button>' : ''}
                </div>
                ${this.sleepTimerEnd ? `<div class="sleep-timer-menu__status">Timer ends at ${new Date(this.sleepTimerEnd).toLocaleTimeString()}</div>` : ''}
            </div>
        `;

        document.body.appendChild(menu);

        // Close on outside click (with proper cleanup)
        if (!this._sleepOutsideClickHandler) {
            this._sleepOutsideClickHandler = (e) => {
                const m = document.getElementById('sleepTimerMenu');
                if (m && !m.contains(e.target) && !e.target.closest('#btnSleepTimer')) {
                    Player.closeSleepTimerMenu();
                }
            };
        }

        if (this._sleepOutsideClickTimeout) {
            clearTimeout(this._sleepOutsideClickTimeout);
        }

        this._sleepOutsideClickTimeout = setTimeout(() => {
            document.addEventListener('click', this._sleepOutsideClickHandler);
            this._sleepOutsideClickTimeout = null;
        }, 100);
    },

    closeSleepTimerMenu() {
        const menu = document.getElementById('sleepTimerMenu');
        if (menu) menu.remove();

        if (this._sleepOutsideClickTimeout) {
            clearTimeout(this._sleepOutsideClickTimeout);
            this._sleepOutsideClickTimeout = null;
        }

        if (this._sleepOutsideClickHandler) {
            document.removeEventListener('click', this._sleepOutsideClickHandler);
        }
    },

    /**
     * Set sleep timer
     */
    setSleepTimer(minutes) {
        if (!minutes || minutes <= 0) {
            this.cancelSleepTimer();
            return;
        }

        this.cancelSleepTimer();

        this.sleepTimerEnd = Date.now() + (minutes * 60 * 1000);

        this.sleepTimer = setTimeout(() => {
            this.pause();
            this.showToast('Sleep timer ended - playback paused');
            this.sleepTimer = null;
            this.sleepTimerEnd = null;
            if (this.sleepTimerInterval) {
                clearInterval(this.sleepTimerInterval);
                this.sleepTimerInterval = null;
            }
            this.updateSleepTimerDisplay();
        }, minutes * 60 * 1000);

        // Start interval to update countdown every second
        this.sleepTimerInterval = setInterval(() => {
            this.updateSleepTimerDisplay();
        }, 1000);

        this.updateSleepTimerDisplay();
        this.showToast(`Sleep timer: ${minutes} min`);
    },

    /**
     * Show sleep timer controls
     * @param {number} minutes - Timer duration
     */
    showSleepTimerControls(minutes) {
        const existing = document.getElementById('sleepTimerControls');
        if (existing) existing.remove();

        const controls = document.createElement('div');
        controls.id = 'sleepTimerControls';
        controls.className = 'sleep-timer-controls';
        controls.innerHTML = `
            <div class="sleep-timer-controls__content">
                <div class="sleep-timer-controls__header">
                    <span>Sleep Timer</span>
                    <button class="sleep-timer-controls__close" onclick="Player.hideSleepTimerControls()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="sleep-timer-controls__display">
                    <span class="sleep-timer-controls__time">${minutes}m</span>
                    <span class="sleep-timer-controls__status">Remaining</span>
                </div>
                <button class="sleep-timer-controls__cancel" onclick="Player.cancelSleepTimer()">
                    <i class="fas fa-times"></i><span>Cancel</span>
                </button>
            </div>
        `;

        document.body.appendChild(controls);

        // Position near sleep timer button
        const sleepBtn = document.getElementById('btnSleepTimer');
        if (sleepBtn) {
            const rect = sleepBtn.getBoundingClientRect();
            controls.style.left = rect.left - 40 + 'px';
            controls.style.top = rect.top - 120 + 'px';
        }

        // Start countdown update
        this.updateSleepTimerCountdown();
    },

    /**
     * Update sleep timer countdown
     */
    updateSleepTimerCountdown() {
        if (!this.sleepTimerEnd) return;

        const remaining = Math.max(0, Math.ceil((this.sleepTimerEnd - Date.now()) / 60000));
        const display = document.querySelector('.sleep-timer-controls__time');
        if (display) {
            display.textContent = `${remaining}m`;
        }

        if (remaining > 0) {
            setTimeout(() => this.updateSleepTimerCountdown(), 30000);
        }
    },

    /**
     * Hide sleep timer controls
     */
    hideSleepTimerControls() {
        const controls = document.getElementById('sleepTimerControls');
        if (controls) controls.remove();
    },

    /**
     * Cancel sleep timer
     */
    cancelSleepTimer() {
        if (this.sleepTimer) {
            clearTimeout(this.sleepTimer);
            this.sleepTimer = null;
        }
        if (this.sleepTimerInterval) {
            clearInterval(this.sleepTimerInterval);
            this.sleepTimerInterval = null;
        }
        if (this.sleepTimerEnd) {
            this.sleepTimerEnd = null;
            this.updateSleepTimerDisplay();
            this.showToast('Sleep timer cancelled');
        }
        this.closeSleepTimerMenu();
    },

    /**
     * Update sleep timer display
     */
    updateSleepTimerDisplay() {
        const display = document.getElementById('sleepTimerDisplay');
        const btn = document.getElementById('btnSleepTimer');
        const btnNP = document.getElementById('btnSleepTimerNP');
        const countdown = document.getElementById('sleepTimerCountdown');
        const floating = document.getElementById('sleepTimerFloating');
        const floatingTime = document.getElementById('sleepTimerFloatingTime');

        if (this.sleepTimerEnd) {
            const remainingMs = Math.max(0, this.sleepTimerEnd - Date.now());
            const remainingMin = Math.ceil(remainingMs / 60000);
            const mins = Math.floor(remainingMs / 60000);
            const secs = Math.floor((remainingMs % 60000) / 1000);
            const timeStr = `${mins}:${secs.toString().padStart(2, '0')}`;

            if (display) display.textContent = `${remainingMin}m`;
            if (btn) btn.classList.add('active');
            if (btnNP) btnNP.classList.add('active');
            if (countdown) {
                countdown.textContent = timeStr;
                countdown.classList.remove('hidden');
            }
            // Show floating indicator
            if (floating) floating.classList.remove('hidden');
            if (floatingTime) floatingTime.textContent = timeStr;
        } else {
            if (display) display.textContent = '';
            if (btn) btn.classList.remove('active');
            if (btnNP) btnNP.classList.remove('active');
            if (countdown) {
                countdown.textContent = '';
                countdown.classList.add('hidden');
            }
            // Hide floating indicator
            if (floating) floating.classList.add('hidden');
            if (floatingTime) floatingTime.textContent = '';
        }
    },

    /**
     * Open Now Playing panel
     */
    openNowPlaying() {
        const panel = document.getElementById('nowPlayingPanel');
        if (!panel) return;

        // Sync current track info
        this.syncNowPlayingUI();

        // Open panel
        panel.classList.add('open');
        document.body.style.overflow = 'hidden';
    },

    /**
     * Close Now Playing panel
     */
    closeNowPlaying() {
        const panel = document.getElementById('nowPlayingPanel');
        if (panel) {
            panel.classList.remove('open');
            document.body.style.overflow = '';
        }
    },

    /**
     * Sync Now Playing UI with current state
     */
    syncNowPlayingUI() {
        const track = this.currentTrack;
        const defaultThumb = '/static/images/default-album.png';

        // Track info
        const thumb = document.getElementById('nowPlayingThumb');
        const title = document.getElementById('nowPlayingTitle');
        const artist = document.getElementById('nowPlayingArtist');

        if (thumb) thumb.src = track?.thumbnail || defaultThumb;
        if (title) title.textContent = track?.title || 'Not Playing';
        if (artist) artist.textContent = track?.artist || '—';

        // Volume
        const volumeSlider = document.getElementById('nowPlayingVolume');
        if (volumeSlider && this.audio) {
            volumeSlider.value = Math.round(this.audio.volume * 100);
        }

        // Update button states
        this.updateNowPlayingButtons();
    },

    /**
     * Update Now Playing button states
     */
    updateNowPlayingButtons() {
        // Play/Pause button
        const playBtn = document.getElementById('btnPlayPauseNP');
        if (playBtn) {
            const isPlaying = this.audio && !this.audio.paused;
            playBtn.innerHTML = isPlaying ? '<i class="fas fa-pause"></i>' : '<i class="fas fa-play"></i>';
        }

        // Shuffle button
        const shuffleBtn = document.getElementById('btnShuffleNP');
        if (shuffleBtn) {
            shuffleBtn.classList.toggle('active', this.shuffle);
        }

        // Repeat button
        const repeatBtn = document.getElementById('btnRepeatNP');
        if (repeatBtn) {
            repeatBtn.classList.toggle('active', this.repeat !== 'off');
            if (this.repeat === 'one') {
                repeatBtn.innerHTML = '<i class="fas fa-repeat"></i><span class="np-repeat-one">1</span>';
            } else {
                repeatBtn.innerHTML = '<i class="fas fa-repeat"></i>';
            }
        }
    },

    /**
     * Update Now Playing progress
     */
    updateNowPlayingProgress() {
        if (!this.audio || isNaN(this.audio.duration)) return;

        const percent = (this.audio.currentTime / this.audio.duration) * 100;

        const fill = document.getElementById('nowPlayingProgress');
        if (fill) fill.style.width = `${percent}%`;

        const timeEl = document.getElementById('nowPlayingTime');
        if (timeEl) timeEl.textContent = this.formatTime(this.audio.currentTime);

        const durationEl = document.getElementById('nowPlayingDuration');
        if (durationEl) durationEl.textContent = this.formatTime(this.audio.duration);
    },

    /**
     * Seek from Now Playing progress bar
     */
    seekFromNowPlaying(event) {
        if (!this.audio || !this.audio.duration || isNaN(this.audio.duration)) return;

        const bar = document.getElementById('nowPlayingProgressBar');
        if (!bar) return;

        const rect = bar.getBoundingClientRect();
        const clientX = event.touches ? event.touches[0].clientX : event.clientX;
        const percent = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));

        this.audio.currentTime = percent * this.audio.duration;
        this.updateNowPlayingProgress();
    },

    /**
     * Show toast notification
     */
    showToast(message) {
        // Simple compact toast
        const existing = document.querySelector('.player-toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = 'player-toast';
        toast.textContent = message;
        document.body.appendChild(toast);

        // Quick show/hide for snappy feedback
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 250);
        }, 1500);
    }
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Player.init());
} else {
    Player.init();
}

// Global wrappers for sleep timer onclick handlers
window.setSleepTimer = (minutes) => Player.setSleepTimer(minutes);
window.cancelSleepTimer = () => Player.cancelSleepTimer();

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Player;
}
