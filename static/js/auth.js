/**
 * Zora - Auth Module
 * Login, signup, logout, password reset, profile management
 * 
 * Dependencies: api.js, ui.js, app.js (State, showView, setupEventListeners, etc.)
 */

// ==================== Auth ====================
function applyRoleUI() {
    const isLoggedIn = !!State.user;
    const isAdmin = isLoggedIn && State.user.role === 'admin';

    // Toggle app chrome visibility
    document.querySelectorAll('.sidebar, .mobile-nav, .mobile-header').forEach(el => {
        el.classList.toggle('hidden', !isLoggedIn);
    });

    // Admin-only nav links & elements
    document.querySelectorAll('[data-role="admin"]').forEach(el => {
        el.classList.toggle('hidden', !isAdmin);
    });

    // Settings buttons (sidebar footer + mobile header)
    document.querySelectorAll('.sidebar__btn--settings, .mobile-header__action--settings').forEach(el => {
        el.classList.toggle('hidden', !isAdmin);
    });

    // Update user info in sidebar footer
    const userInfo = document.getElementById('sidebarUserInfo');
    if (userInfo && isLoggedIn) {
        const initials = (State.user.name || State.user.email || '?').charAt(0).toUpperCase();
        userInfo.innerHTML = `
            <div class="sidebar-user">
                <div class="sidebar-user__avatar">${UI.escapeHtml(initials)}</div>
                <div class="sidebar-user__details">
                    <span class="sidebar-user__name">${UI.escapeHtml(State.user.name)}</span>
                    <span class="sidebar-user__role">${UI.escapeHtml(State.user.role)}</span>
                </div>
                <button class="sidebar-user__logout" onclick="handleLogout()" title="Log out">
                    <i class="fas fa-sign-out-alt"></i>
                </button>
            </div>
        `;
    }
}

async function handleLogin(e) {
    e?.preventDefault();
    const email = document.getElementById('loginEmail')?.value?.trim();
    const password = document.getElementById('loginPassword')?.value;

    if (!email || !password) {
        UI.toast('Please enter email and password', 'error');
        return;
    }

    const btn = document.getElementById('loginBtn');
    if (btn) btn.disabled = true;

    try {
        const user = await API.auth.login(email, password);
        State.user = user;
        // Re-init the full app
        applyRoleUI();
        Player.init();
        setupEventListeners();
        setupLibraryLazyLoading();
        adjustMainPadding();
        window.addEventListener('resize', adjustMainPadding);
        if (State.user.role === 'admin') await loadSettings();
        await loadHistory();
        await loadPlaylists();
        showView('library');
        UI.toast(`Welcome back, ${user.name}!`, 'success');
    } catch (error) {
        UI.toast(error.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function handleSignup(e) {
    e?.preventDefault();
    const name = document.getElementById('signupName')?.value?.trim();
    const email = document.getElementById('signupEmail')?.value?.trim();
    const password = document.getElementById('signupPassword')?.value;
    const confirm = document.getElementById('signupConfirmPassword')?.value;

    if (!name || !email || !password || !confirm) {
        UI.toast('Please fill in all fields', 'error');
        return;
    }

    const btn = document.getElementById('signupBtn');
    if (btn) btn.disabled = true;

    try {
        const user = await API.auth.signup(name, email, password, confirm);
        State.user = user;
        applyRoleUI();
        Player.init();
        setupEventListeners();
        setupLibraryLazyLoading();
        adjustMainPadding();
        window.addEventListener('resize', adjustMainPadding);
        await loadHistory();
        await loadPlaylists();
        showView('library');
        UI.toast(`Welcome to Zora, ${user.name}!`, 'success');
    } catch (error) {
        UI.toast(error.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function handleLogout() {
    try {
        await API.auth.logout();
    } catch (_) {
        // Ignore — we'll clear state regardless
    }

    // Stop playback
    if (typeof Player !== 'undefined' && Player.audio) {
        Player.audio.pause();
        Player.audio.src = '';
    }

    // Clear all app state
    State.user = null;
    State.downloads = [];
    State.playlists.list = [];
    State.playlists.selectedId = null;
    State.playlists.songs = [];
    State.playlists.addModalSongId = null;
    State.playlists.addSongsModalTargetPlaylistId = null;
    State.playlists.addSongsModalSearch = '';
    State.playlists.addSongsModalAddingIds = new Set();
    State.playlists.listSearch = '';
    State.playback.queue = [];
    State.playback.source = 'library';
    State.playback.playlistId = null;
    State.currentVideo = null;
    State.lastDownloaded = null;
    State.currentJobId = null;
    State.library.visibleCount = 0;
    State.library.searchQuery = '';

    // Stop any active playlist download polling
    if (State.playlistPollInterval) {
        clearInterval(State.playlistPollInterval);
        State.playlistPollInterval = null;
    }
    State.playlistSession = null;
    localStorage.removeItem('playlist_download_session');

    // Clear cached audio to prevent cross-user data leak
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_AUDIO_CACHE' });
    }

    // Clear UI elements
    const libraryGrid = document.getElementById('libraryGrid');
    if (libraryGrid) libraryGrid.innerHTML = '';
    const playlistsList = document.getElementById('playlistsList');
    if (playlistsList) playlistsList.innerHTML = '';
    const sidebarUserInfo = document.getElementById('sidebarUserInfo');
    if (sidebarUserInfo) sidebarUserInfo.innerHTML = '';

    // Hide player bar
    const playerBar = document.getElementById('playerBar');
    if (playerBar) playerBar.classList.add('hidden');

    applyRoleUI();
    showView('login');
}

function switchAuthTab(tab) {
    if (tab === 'signup') {
        showView('signup');
    } else if (tab === 'forgot-password') {
        showView('forgot-password');
    } else if (tab === 'reset-password') {
        showView('reset-password');
    } else {
        showView('login');
    }
}

async function handleForgotPassword(event) {
    event.preventDefault();
    const email = document.getElementById('forgotEmail').value.trim();
    const btn = document.getElementById('forgotPasswordBtn');

    if (!email) {
        UI.toast('Please enter your email', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';

    try {
        const result = await API.auth.requestPasswordReset(email);
        UI.toast(result.message || 'If an account exists, a reset link has been sent.', 'success');
        document.getElementById('forgotEmail').value = '';
    } catch (error) {
        UI.toast(error.message || 'Failed to send reset link', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane"></i> Send Reset Link';
    }
}

async function handleResetPassword(event) {
    event.preventDefault();
    const newPassword = document.getElementById('resetNewPassword').value;
    const confirmPassword = document.getElementById('resetConfirmPassword').value;
    const btn = document.getElementById('resetPasswordBtn');

    if (newPassword.length < 8) {
        UI.toast('Password must be at least 8 characters', 'error');
        return;
    }
    if (newPassword !== confirmPassword) {
        UI.toast('Passwords do not match', 'error');
        return;
    }

    // Get token from URL
    const params = new URLSearchParams(window.location.search);
    const token = params.get('reset_token');
    if (!token) {
        UI.toast('Invalid reset link', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Resetting...';

    try {
        const result = await API.auth.confirmPasswordReset(token, newPassword);
        UI.toast(result.message || 'Password reset! You can now sign in.', 'success');
        window.history.replaceState({}, '', '/');
        switchAuthTab('login');
    } catch (error) {
        UI.toast(error.message || 'Failed to reset password', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-key"></i> Reset Password';
    }
}

// ==================== Profile ====================
function loadProfile() {
    if (!State.user) return;

    const initials = (State.user.name || State.user.email || '?').charAt(0).toUpperCase();
    const avatarEl = document.getElementById('profileAvatar');
    if (avatarEl) {
        if (State.user.avatar_url) {
            avatarEl.innerHTML = `<img src="${UI.escapeHtml(State.user.avatar_url)}" alt="Avatar" class="profile-card__avatar-img">`;
        } else {
            avatarEl.textContent = initials;
        }
    }

    const nameInput = document.getElementById('profileNameInput');
    if (nameInput) nameInput.value = State.user.name || '';

    const emailEl = document.getElementById('profileEmail');
    if (emailEl) emailEl.textContent = State.user.email || '';

    const roleEl = document.getElementById('profileRole');
    if (roleEl) {
        roleEl.textContent = State.user.role === 'admin' ? 'Administrator' : 'User';
        roleEl.className = 'profile-badge profile-badge--' + State.user.role;
    }

    const authEl = document.getElementById('profileAuthProvider');
    if (authEl) {
        const providers = { local: 'Email & Password', google: 'Google', hybrid: 'Email & Google' };
        authEl.textContent = providers[State.user.auth_provider] || State.user.auth_provider;
    }

    const createdEl = document.getElementById('profileCreatedAt');
    if (createdEl && State.user.created_at) {
        createdEl.textContent = new Date(State.user.created_at).toLocaleDateString('en-US', {
            year: 'numeric', month: 'long', day: 'numeric'
        });
    }

    // Hide password section for Google-only users
    const pwSection = document.getElementById('profilePasswordSection');
    if (pwSection) {
        pwSection.classList.toggle('hidden', State.user.auth_provider === 'google');
    }
}

async function handleSaveProfileName() {
    const nameInput = document.getElementById('profileNameInput');
    const btn = document.getElementById('profileSaveNameBtn');
    const name = nameInput?.value?.trim();

    if (!name) {
        UI.toast('Name cannot be empty', 'error');
        return;
    }

    btn.disabled = true;
    try {
        const updated = await API.auth.updateProfile({ name });
        State.user = updated;
        applyRoleUI();
        UI.toast('Name updated', 'success');
    } catch (error) {
        UI.toast(error.message || 'Failed to update name', 'error');
    } finally {
        btn.disabled = false;
    }
}

async function handleProfilePasswordChange(event) {
    event.preventDefault();
    const currentPw = document.getElementById('profileCurrentPassword').value;
    const newPw = document.getElementById('profileNewPassword').value;
    const btn = document.getElementById('profileChangePasswordBtn');

    if (newPw.length < 8) {
        UI.toast('New password must be at least 8 characters', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Changing...';

    try {
        await API.auth.changePassword(currentPw, newPw);
        UI.toast('Password changed successfully', 'success');
        document.getElementById('profileCurrentPassword').value = '';
        document.getElementById('profileNewPassword').value = '';
    } catch (error) {
        UI.toast(error.message || 'Failed to change password', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-key"></i> Change Password';
    }
}
