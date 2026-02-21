/**
 * Zora - Main Application
 * YouTube Music Downloader
 * 
 * Core: State, initialization, confirm modal, view routing
 * 
 * Dependencies: ui.js, api.js, player.js
 * Loaded before: auth.js, downloads.js, playlists.js, library.js, playback.js, admin.js
 */

// ==================== State ====================
const State = {
    user: null,            // Current user object from /api/auth/me
    mode: 'url',           // 'url', 'playlist', or 'search'
    format: 'm4a',
    quality: '320',
    currentJobId: null,
    pollInterval: null,
    currentVideo: null,
    lastDownloaded: null,
    downloads: [],
    playlists: {
        items: [],
        selectedId: null,
        songs: [],
        addModalSongId: null,
        addSongsModalTargetPlaylistId: null,
        addSongsModalSearch: '',
        addSongsModalAddingIds: new Set(),
        listSearch: '',
        workspace: 'library'
    },
    playback: {
        queue: [],
        source: 'library',
        playlistId: null
    },
    library: {
        batchSize: 24,
        visibleCount: 0,
        observer: null,
        scrollListenerAttached: false,
        viewMode: 'grid',
        searchQuery: ''
    },
    playlist: {
        items: [],
        selected: new Set(),
        title: '',
        autoCreate: false
    },
    playlistSession: null,
    playlistPollInterval: null,
    confirmAction: {
        active: false,
        resolver: null,
        requireText: ''
    },
    // Server-synced preferences buffer
    _prefsSyncPending: {},
    _prefsSyncTimer: null
};

// ==================== Preference Sync ====================
/**
 * Queue a preference change for debounced server sync.
 * Call this whenever a user preference changes.
 */
function syncPreferencesToServer(key, value) {
    if (!State.user) return; // Not logged in

    State._prefsSyncPending[key] = String(value);

    // Debounce: wait 2 seconds of inactivity before sending
    if (State._prefsSyncTimer) clearTimeout(State._prefsSyncTimer);
    State._prefsSyncTimer = setTimeout(async () => {
        const prefs = { ...State._prefsSyncPending };
        State._prefsSyncPending = {};

        try {
            await API.preferences.save(prefs);
        } catch (err) {
            console.warn('Failed to sync preferences:', err.message);
        }
    }, 2000);
}

/**
 * Apply server preferences over localStorage defaults.
 * Called once after login/init.
 */
async function loadServerPreferences() {
    try {
        const prefs = await API.preferences.get();
        if (!prefs || typeof prefs !== 'object') return;

        // Apply to player
        if (prefs.player_volume !== undefined && Player.audio) {
            Player.audio.volume = parseFloat(prefs.player_volume) || 1;
            Player.syncVolumeSliders?.();
        }
        if (prefs.player_shuffle !== undefined) {
            Player.shuffle = prefs.player_shuffle === 'true';
            Player.updateShuffleButton?.();
        }
        if (prefs.player_repeat !== undefined) {
            Player.repeat = prefs.player_repeat;
            Player.updateRepeatButton?.();
        }

        // Apply to library
        if (prefs.library_view_mode !== undefined) {
            State.library.viewMode = prefs.library_view_mode;
        }

        // Store resume data for later (after history loads)
        if (prefs.last_track_filename) {
            State._pendingResume = {
                filename: prefs.last_track_filename,
                title: prefs.last_track_title || 'Unknown Title',
                artist: prefs.last_track_artist || 'Unknown Artist',
                thumbnail: prefs.last_track_thumbnail || '',
                position: parseFloat(prefs.last_track_position) || 0
            };
        }


        console.log('✅ Preferences loaded from server');
    } catch (err) {
        console.warn('Could not load server preferences:', err.message);
    }
}

/**
 * Resume last playback from saved state.
 * Loads the track in PAUSED state and seeks to the saved position.
 * User must press play to continue.
 */
function resumeLastPlayback() {
    // Try server prefs first, fall back to localStorage
    let resume = State._pendingResume || null;

    if (!resume) {
        try {
            const saved = localStorage.getItem('last_playback_state');
            if (saved) resume = JSON.parse(saved);
        } catch (e) { /* ignore parse errors */ }
    }

    if (!resume || !resume.filename) return;

    // Verify the track still exists in the library
    const track = State.downloads.find(d => d.filename === resume.filename);
    if (!track) {
        console.log('Resume track not found in library, skipping');
        return;
    }

    // Build queue and set up the track
    if (typeof buildLibraryPlaybackQueue === 'function' && typeof setPlaybackQueue === 'function') {
        const queue = buildLibraryPlaybackQueue();
        const matchIdx = queue.findIndex(t => t.filename === resume.filename);
        if (matchIdx !== -1) {
            setPlaybackQueue('library', queue, matchIdx, null);
        }
    }

    // Load the track into the player without auto-playing
    Player.play(resume.filename, resume.title, resume.artist, resume.thumbnail);

    // Seek to saved position and pause (let user press play to resume)
    if (Player.audio) {
        const seekPosition = resume.position || 0;
        if (seekPosition > 0) {
            const seekOnReady = () => {
                Player.audio.currentTime = seekPosition;
                Player.audio.pause();
                Player._lastSavedPosition = seekPosition;
                Player.audio.removeEventListener('canplay', seekOnReady);
                console.log(`Resume ready: "${resume.title}" at ${Math.floor(seekPosition)}s`);
            };
            Player.audio.addEventListener('canplay', seekOnReady);
        } else {
            setTimeout(() => Player.audio?.pause(), 100);
        }
    }

    // Clean up
    delete State._pendingResume;
}

// ==================== Initialize ====================
document.addEventListener('DOMContentLoaded', () => {
    init();
});

async function init() {
    // Check authentication first
    const user = await API.auth.me();

    if (!user) {
        // Not logged in — show login view, hide app chrome
        State.user = null;
        applyRoleUI();

        const params = new URLSearchParams(window.location.search);

        // Check for password reset token FIRST (before any replaceState clears URL)
        const resetToken = params.get('reset_token');
        if (resetToken) {
            showView('reset-password');
            return;
        }

        // Check for Google OAuth error in URL
        const oauthError = params.get('error');
        if (oauthError) {
            const messages = {
                google_not_configured: 'Google login is not configured on this server.',
                google_auth_failed: 'Google authentication failed. Please try again.',
                google_userinfo_failed: 'Could not retrieve your Google account info.',
                google_no_email: 'No email returned from Google.',
                google_email_not_verified: 'Your Google email is not verified.',
                account_disabled: 'Your account has been disabled. Contact the admin.',
            };
            UI.toast(messages[oauthError] || 'Login failed. Please try again.', 'error');
            window.history.replaceState({}, '', '/');
        }

        showView('login');
        return;
    }

    // Authenticated — store user and boot app
    State.user = user;
    applyRoleUI();

    // Initialize player
    Player.init();

    // Setup event listeners
    setupEventListeners();
    setupLibraryLazyLoading();

    // Adjust main content padding based on player height
    adjustMainPadding();
    window.addEventListener('resize', adjustMainPadding);

    // Restore playlist download session from localStorage
    const savedSession = localStorage.getItem('playlist_download_session');
    if (savedSession) {
        State.playlistSession = savedSession;
        startPlaylistPolling();
    }

    const savedLibraryViewMode = localStorage.getItem('library_view_mode');
    if (savedLibraryViewMode === 'grid' || savedLibraryViewMode === 'list') {
        State.library.viewMode = savedLibraryViewMode;
    }

    // Load server-synced preferences (override localStorage defaults)
    await loadServerPreferences();

    // Load data based on role
    if (State.user.role === 'admin') {
        await loadSettings();
    }
    await loadHistory();
    await loadPlaylists();

    // Resume last track (after history is loaded so queue can be built)
    resumeLastPlayback();

    // Show default view
    showView('library');

    // Show cookie consent banner if not yet dismissed
    showCookieConsent();
}

function setupEventListeners() {
    // Enter key on search input
    const input = document.getElementById('mainInput');
    if (input) {
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleMainAction();
        });
    }

    const previewOption = document.getElementById('autoCreatePlaylistCheckbox');
    if (previewOption) {
        previewOption.addEventListener('change', (e) => {
            setPlaylistAutoCreateState(Boolean(e.target?.checked));
        });
    }

    const librarySearchInput = document.getElementById('librarySearchInput');
    if (librarySearchInput) {
        librarySearchInput.addEventListener('input', (event) => {
            filterLibrary(event.target?.value || '');
        });
    }

    const confirmInput = document.getElementById('confirmActionInput');
    if (confirmInput) {
        confirmInput.addEventListener('input', updateConfirmActionSubmitState);
        confirmInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                submitConfirmAction();
            }
        });
    }

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && State.confirmAction.active) {
            cancelConfirmAction();
            return;
        }

        if (event.key !== 'Escape') return;

        const addSongsModalOpen = !document.getElementById('addSongsToPlaylistModal')?.classList.contains('hidden');
        const addToPlaylistModalOpen = !document.getElementById('addToPlaylistModal')?.classList.contains('hidden');

        if (addSongsModalOpen) {
            closeAddSongsToSelectedPlaylistModal();
        } else if (addToPlaylistModalOpen) {
            closeAddToPlaylistModal();
        } else {
            closeAllLibraryActionMenus();
        }
    });

    document.addEventListener('click', (event) => {
        if (event.target?.closest('.library-card__menu-wrap')) return;
        closeAllLibraryActionMenus();
    });
}

// ==================== Dynamic Padding for Player ====================
function adjustMainPadding() {
    const player = document.getElementById('playerBar');
    const mobileNav = document.querySelector('.mobile-nav');
    const main = document.getElementById('mainContent');

    if (!main) return;

    // Calculate total height of fixed bottom elements
    let bottomHeight = 0;

    if (player && !player.classList.contains('hidden')) {
        bottomHeight += player.offsetHeight;
    }

    if (mobileNav && window.getComputedStyle(mobileNav).display !== 'none') {
        bottomHeight += mobileNav.offsetHeight;
    }

    // Add extra padding for safe area and breathing room
    const extraPadding = 20;
    main.style.paddingBottom = (bottomHeight + extraPadding) + 'px';
}

// ==================== Confirm Action Modal ====================
function updateConfirmActionSubmitState() {
    const submitBtn = document.getElementById('confirmActionSubmitBtn');
    if (!submitBtn) return;

    const expected = String(State.confirmAction.requireText || '').trim().toLowerCase();
    if (!expected) {
        submitBtn.disabled = false;
        return;
    }

    const typed = String(document.getElementById('confirmActionInput')?.value || '')
        .trim()
        .toLowerCase();
    submitBtn.disabled = typed !== expected;
}

function closeConfirmActionModal(confirmed) {
    const resolver = State.confirmAction.resolver;
    State.confirmAction.active = false;
    State.confirmAction.resolver = null;
    State.confirmAction.requireText = '';

    const input = document.getElementById('confirmActionInput');
    const inputGroup = document.getElementById('confirmActionInputGroup');
    const submitBtn = document.getElementById('confirmActionSubmitBtn');

    if (input) input.value = '';
    if (inputGroup) inputGroup.classList.add('hidden');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.classList.remove('btn--primary');
        submitBtn.classList.add('btn--danger');
    }

    UI.hide('confirmActionModal');

    if (typeof resolver === 'function') {
        resolver(Boolean(confirmed));
    }
}

function cancelConfirmAction() {
    closeConfirmActionModal(false);
}

function submitConfirmAction() {
    const submitBtn = document.getElementById('confirmActionSubmitBtn');
    if (submitBtn?.disabled) return;
    closeConfirmActionModal(true);
}

function closeConfirmActionOnOverlay(event) {
    if (event?.target?.id === 'confirmActionModal') {
        cancelConfirmAction();
    }
}

function openConfirmAction(options = {}) {
    const {
        title = 'Confirm Action',
        message = 'Are you sure you want to continue?',
        confirmLabel = 'Confirm',
        danger = true,
        requireText = '',
        inputHint = ''
    } = options;

    if (State.confirmAction.active && typeof State.confirmAction.resolver === 'function') {
        State.confirmAction.resolver(false);
    }

    const titleEl = document.getElementById('confirmActionTitle');
    const messageEl = document.getElementById('confirmActionMessage');
    const inputEl = document.getElementById('confirmActionInput');
    const inputGroup = document.getElementById('confirmActionInputGroup');
    const inputLabel = document.getElementById('confirmActionInputLabel');
    const inputHintEl = document.getElementById('confirmActionInputHint');
    const submitBtn = document.getElementById('confirmActionSubmitBtn');

    if (!titleEl || !messageEl || !inputGroup || !submitBtn) {
        return Promise.resolve(false);
    }

    titleEl.innerHTML = `<i class="fas ${danger ? 'fa-triangle-exclamation' : 'fa-circle-info'}"></i> ${UI.escapeHtml(title)}`;
    messageEl.textContent = message;
    submitBtn.innerHTML = `${danger ? '<i class="fas fa-trash"></i>' : '<i class="fas fa-check"></i>'}<span>${UI.escapeHtml(confirmLabel)}</span>`;
    submitBtn.classList.toggle('btn--danger', Boolean(danger));
    submitBtn.classList.toggle('btn--primary', !danger);

    const required = String(requireText || '').trim();
    State.confirmAction.requireText = required;
    State.confirmAction.active = true;

    if (required) {
        inputGroup.classList.remove('hidden');
        if (inputEl) {
            inputEl.value = '';
            inputEl.placeholder = required;
        }
        if (inputLabel) {
            inputLabel.textContent = 'Type to confirm';
        }
        if (inputHintEl) {
            inputHintEl.textContent = inputHint || `Type "${required}" to continue.`;
        }
    } else {
        inputGroup.classList.add('hidden');
        if (inputEl) inputEl.value = '';
        if (inputHintEl) inputHintEl.textContent = '';
    }

    updateConfirmActionSubmitState();
    UI.show('confirmActionModal');

    setTimeout(() => {
        if (required && inputEl) {
            inputEl.focus();
        } else {
            submitBtn.focus();
        }
    }, 10);

    return new Promise((resolve) => {
        State.confirmAction.resolver = resolve;
    });
}

// ==================== Views ====================
function showView(viewName) {
    // Auth views — no nav, no chrome
    if (viewName === 'login' || viewName === 'signup' || viewName === 'forgot-password' || viewName === 'reset-password') {
        document.querySelectorAll('.view').forEach(view => view.classList.add('hidden'));
        const authViewMap = {
            'login': 'loginView',
            'signup': 'signupView',
            'forgot-password': 'forgotPasswordView',
            'reset-password': 'resetPasswordView'
        };
        const viewId = authViewMap[viewName] || 'loginView';
        document.getElementById(viewId)?.classList.remove('hidden');
        return;
    }

    // View name mapping for nav matching
    const viewNavMap = {
        'download': 'download',
        'library': 'library',
        'playlists': 'playlists',
        'playlist-downloads': 'playlist-downloads',
        'admin': 'admin',
        'profile': 'profile'
    };
    const navName = viewNavMap[viewName] || viewName;

    // Update nav using data attribute or text matching
    document.querySelectorAll('.nav-link').forEach(link => {
        const linkView = link.dataset.view || link.textContent.toLowerCase().trim();
        link.classList.toggle('active', linkView === navName);
    });

    // Update views
    document.querySelectorAll('.view').forEach(view => view.classList.add('hidden'));

    if (viewName === 'download') {
        document.getElementById('downloadView')?.classList.remove('hidden');
    } else if (viewName === 'library') {
        document.getElementById('libraryView')?.classList.remove('hidden');
        loadHistory().catch((error) => {
            console.error('Failed to refresh library view:', error);
            updateLibrary();
        });
        requestAnimationFrame(maybeLoadMoreLibraryByScroll);
    } else if (viewName === 'playlists') {
        document.getElementById('playlistsView')?.classList.remove('hidden');
        switchPlaylistWorkspace(State.playlists.workspace || 'library', { silent: true });
        loadPlaylists(true).catch((error) => {
            console.error('Failed to refresh playlists view:', error);
        });
    } else if (viewName === 'playlist-downloads') {
        document.getElementById('playlistDownloadsView')?.classList.remove('hidden');
    } else if (viewName === 'profile') {
        document.getElementById('profileView')?.classList.remove('hidden');
        loadProfile();
    } else if (viewName === 'admin') {
        document.getElementById('adminView')?.classList.remove('hidden');
        loadAdminUsers(1);
    }

    // Update mobile nav if function exists
    if (typeof updateMobileNav === 'function') {
        updateMobileNav(viewName);
    }
}

// ==================== Cookie Consent ====================
function showCookieConsent() {
    if (localStorage.getItem('zora_cookie_consent') === 'accepted') return;

    const banner = document.createElement('div');
    banner.id = 'cookieConsentBanner';
    banner.className = 'cookie-consent';
    banner.innerHTML = `
        <div class="cookie-consent__content">
            <span class="cookie-consent__icon">🍪</span>
            <p class="cookie-consent__text">
                Zora uses cookies to remember your preferences (volume, view mode, etc.). No tracking or analytics.
            </p>
            <button class="cookie-consent__btn" onclick="dismissCookieConsent()">
                Got it
            </button>
        </div>
    `;
    document.body.appendChild(banner);

    // Animate in
    requestAnimationFrame(() => {
        banner.classList.add('cookie-consent--visible');
    });
}

function dismissCookieConsent() {
    localStorage.setItem('zora_cookie_consent', 'accepted');
    const banner = document.getElementById('cookieConsentBanner');
    if (banner) {
        banner.classList.remove('cookie-consent--visible');
        setTimeout(() => banner.remove(), 400);
    }
}

// ==================== PWA: Service Worker + Install Prompt ====================

(function initPWA() {
    // 1. Register service worker
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js', { scope: '/' })
                .then(reg => {
                    console.log('[SW] Registered, scope:', reg.scope);

                    // Prompt user to refresh when a new SW version is waiting
                    reg.addEventListener('updatefound', () => {
                        const newWorker = reg.installing;
                        newWorker?.addEventListener('statechange', () => {
                            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                                showUpdateBanner();
                            }
                        });
                    });
                })
                .catch(err => console.warn('[SW] Registration failed:', err));
        });
    }

    // 2. Install prompt (Chrome/Edge/Android)
    let _installPrompt = null;

    window.addEventListener('beforeinstallprompt', e => {
        e.preventDefault();
        _installPrompt = e;

        // Only show if not already installed and user hasn't dismissed recently
        const dismissed = localStorage.getItem('zora_install_dismissed');
        const cooldown = 3 * 24 * 60 * 60 * 1000; // 3 days
        const isStandalone = window.matchMedia('(display-mode: standalone)').matches;

        if (!isStandalone && (!dismissed || Date.now() - Number(dismissed) > cooldown)) {
            showInstallBanner();
        }
    });

    window.zoraTriggerInstallPrompt = async () => {
        if (!_installPrompt) return;
        _installPrompt.prompt();
        const { outcome } = await _installPrompt.userChoice;
        _installPrompt = null;
        dismissInstallBanner();
        if (outcome === 'accepted') {
            console.log('[PWA] User installed the app');
        }
    };

    function showInstallBanner() {
        if (document.getElementById('zoraInstallBanner')) return;

        const banner = document.createElement('div');
        banner.id = 'zoraInstallBanner';
        banner.className = 'pwa-install-banner';
        banner.innerHTML = `
            <div class="pwa-install-banner__icon">
                <img src="/static/images/icons/icon-72x72.png" alt="Zora">
            </div>
            <div class="pwa-install-banner__text">
                <strong>Install Zora</strong>
                <span>Add to your home screen for the best experience</span>
            </div>
            <div class="pwa-install-banner__actions">
                <button class="pwa-install-banner__btn pwa-install-banner__btn--primary" onclick="zoraTriggerInstallPrompt()">
                    Install
                </button>
                <button class="pwa-install-banner__btn" onclick="dismissInstallBanner()">
                    Not now
                </button>
            </div>`;

        document.body.appendChild(banner);

        // Auto-dismiss after 10 seconds
        setTimeout(() => dismissInstallBanner(false), 10000);

        requestAnimationFrame(() => banner.classList.add('pwa-install-banner--visible'));
    }

    window.dismissInstallBanner = (remember = true) => {
        if (remember) localStorage.setItem('zora_install_dismissed', Date.now());
        const banner = document.getElementById('zoraInstallBanner');
        if (banner) {
            banner.classList.remove('pwa-install-banner--visible');
            setTimeout(() => banner.remove(), 400);
        }
    };

    // 3. Update available banner
    function showUpdateBanner() {
        if (document.getElementById('zoraUpdateBanner')) return;

        const banner = document.createElement('div');
        banner.id = 'zoraUpdateBanner';
        banner.className = 'pwa-update-banner pwa-update-banner--visible';
        banner.innerHTML = `
            <i class="fas fa-sync-alt"></i>
            <span>A new version of Zora is available</span>
            <button onclick="window.location.reload()">Refresh</button>
            <button onclick="this.closest('.pwa-update-banner').remove()"><i class="fas fa-times"></i></button>`;

        document.body.appendChild(banner);
    }
})();
