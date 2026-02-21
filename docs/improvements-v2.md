# Zora v2 — Improvements & Bug Fixes

> **Created:** 2026-02-20  
> **Status:** Steps 5.1–5.5 Complete ✅ | Step 5.6 (modularize) pending  
> **Scope:** Reliability fixes, user profile, audio compatibility, modularity

---

## Issues Identified

| # | Issue | Severity | Category |
|---|---|---|---|
| 1 | "Failed to fetch" on password reset confirm | 🔴 Critical | Auth |
| 2 | Password reset — `reset_token` cleared before API call on OAuth error redirect | 🔴 Critical | Auth |
| 3 | Logout leaves stale UI state (content visible briefly, player state leaks) | 🟡 Medium | Auth/UI |
| 4 | No user profile section (can't change name, view account info) | 🟡 Medium | Feature |
| 5 | "Audio format not supported" on some downloads (opus/webm/mka) | 🟡 Medium | Playback |
| 6 | `showToast` used in OAuth error handler (undefined, should be `UI.toast`) | 🟠 Low | Bug |
| 7 | App code is monolithic (~2800 lines in app.js) | 🟠 Low | Code quality |

---

## Phase 5 — Reliability + UX Improvements

> Estimate: ~4–6 hours across 7 steps

---

### Step 5.1 — Fix password reset reliability

> Priority: 🔴 Critical  
> Effort: ~20 minutes

**Problems:**
1. `handleResetPassword()` gets "failed to fetch" because the `reset_token` URL param is cleared by the OAuth error check on line 85 (`window.history.replaceState({}, '', '/')`) BEFORE the reset token check on line 89
2. Rate limiter (5/min on confirm endpoint) triggers if user retries
3. No loading/error states shown during the reset flow

**Fixes (all completed ✅):**

- [x] **Fix URL param order in `init()`** — check `reset_token` BEFORE OAuth error handling, not after
- [x] **Don't clear URL until reset is submitted** — `replaceState` only in success handler
- [x] **Fix `showToast` → `UI.toast`** in OAuth error handler
- [x] **Increase rate limit** on `confirm_password_reset` to `10 per minute`

**Files:** `static/js/app.js`, `app/auth/routes.py`

---

### Step 5.2 — Fix logout cleanup

> Priority: 🟡 Medium  
> Effort: ~30 minutes

**Problems:**
1. After logout, `State.downloads`, `State.playlists`, `State.playback` still hold old data
2. Player may still be playing audio after logout
3. If user logs in as different account, stale data from previous session shows briefly

**Fixes (all completed ✅):**

- [x] **Stop player on logout** — pauses audio, clears source
- [x] **Reset all State** — clears downloads, playlists, playback queue, library state
- [x] **Clear UI elements** — empties library grid, playlists list, sidebar user info, hides player bar
- [x] **Clean login transition** — `applyRoleUI()` hides app chrome before showing login

**Files:** `static/js/app.js`

---

### Step 5.3 — User profile section

> Priority: 🟡 Medium  
> Effort: ~1.5 hours

**Completed ✅:**

- [x] `PATCH /api/auth/profile` — update name (validated, max 100 chars)
- [x] `API.auth.updateProfile()` frontend method
- [x] Profile view with: avatar/initials, editable name, email (read-only), role badge, auth provider, member since
- [x] "Change Password" form (hidden for Google-only users)
- [x] "Profile" nav link in sidebar
- [x] Profile card CSS with dark theme styling

**Files:** `app/auth/routes.py`, `templates/index.html`, `static/js/app.js`, `static/js/api.js`, `static/css/style.css`

---

### Step 5.4 — Fix audio format compatibility

> Priority: 🟡 Medium  
> Effort: ~45 minutes

**Problems:**
1. Some downloads save as `.opus`, `.webm`, or `.mka` which browsers can't play natively
2. FFmpeg conversion in `_convert_audio_to_m4a()` runs synchronously on each play request — slow and blocks the server
3. If FFmpeg isn't installed (Termux), conversion silently fails and serves unplayable file
4. MIME type for `.opus` returns `audio/opus` which Safari doesn't support

**Fixes (all completed ✅):**

- [x] **Convert at download time** — `_ensure_browser_compatible_audio()` called after yt-dlp finishes, before saving to DB
- [x] **Both single and playlist downloads** — conversion hook added to `_background_download()` and `_background_playlist_download()`
- [x] **Fix MIME type** — `.opus` served as `audio/ogg` (Safari compatible)
- [x] Play-time conversion still works as fallback for existing files

**Files:** `app/routes/stream.py`, `app/routes/download.py`

---

### Step 5.5 — Fix `showToast` bug

> Priority: 🟠 Low  
> Effort: ~5 minutes

**Problem:** Line 84 in `app.js` calls `showToast()` which doesn't exist as a global function. Should be `UI.toast()`.

**Fixed ✅** — replaced `showToast(...)` with `UI.toast(...)` (done as part of Step 5.1)

**Files:** `static/js/app.js`

---

### Step 5.6 — Modularize app.js

> Priority: 🟠 Low  
> Effort: ~2 hours

**Problem:** `app.js` is ~2800 lines — auth, library, playlists, downloads, admin panel, all in one file. Hard to maintain.

**Plan — split into focused modules:**

```
static/js/
├── api.js              ← already separate (keep)
├── player.js           ← already separate (keep)
├── ui.js               ← already separate (keep)
├── app.js              ← init, routing, state (slim: ~200 lines)
├── auth.js             ← NEW: login, signup, logout, reset, profile (~200 lines)
├── library.js          ← NEW: library grid, search, lazy loading (~300 lines)
├── playlists.js        ← NEW: playlist CRUD, playback queue (~400 lines)
├── downloads.js        ← NEW: download flow, URL/search/playlist tabs (~400 lines)
├── admin.js            ← NEW: admin panel, user management, audit logs (~300 lines)
└── playlist-downloads.js ← NEW: batch playlist download (~200 lines)
```

**Approach:**
- [ ] Each module is an IIFE or object that registers itself on `window`
- [ ] Shared state stays in `State` object (in `app.js`)
- [ ] Shared helpers stay in `ui.js` (toast, escapeHtml, etc.)
- [ ] Load order in `index.html`: `ui.js → api.js → player.js → auth.js → library.js → playlists.js → downloads.js → admin.js → playlist-downloads.js → app.js`
- [ ] `app.js` becomes the orchestrator — just `init()`, `showView()`, `State`, and `setupEventListeners()`

**Done when:** Same functionality, each file under 400 lines, no circular dependencies.

---

### Step 5.7 — Phase 5 smoke test

- [ ] Password reset: request → email/console → click link → new password → login ✅
- [ ] Logout: all state cleared, player stopped, no stale data on re-login ✅
- [ ] Profile: view profile, change name, change password ✅
- [ ] Audio: download opus/webm → plays in Chrome, Safari, Firefox ✅
- [ ] Google OAuth error → toast shown (not silent failure) ✅
- [ ] All existing tests pass ✅

---

## Dependency Graph

```
5.1 Fix password reset ──────────┐
5.2 Fix logout cleanup ──────────┤
5.3 User profile ────────────────┤ (all independent)
5.4 Fix audio format ────────────┤
5.5 Fix showToast bug ───────────┤
                                 ├──→ 5.7 Smoke test
5.6 Modularize app.js ───────────┘     (after all)
```

Steps 5.1–5.5 are independent and can be done in any order.  
Step 5.6 (modularize) should be done last since it touches all JS files.  
Step 5.7 runs after everything.

---

## Files Changed Summary

| File | Steps |
|---|---|
| `static/js/app.js` | 5.1, 5.2, 5.3, 5.5, 5.6 |
| `static/js/api.js` | 5.3 |
| `static/js/auth.js` (new) | 5.6 |
| `static/js/library.js` (new) | 5.6 |
| `static/js/playlists.js` (new) | 5.6 |
| `static/js/downloads.js` (new) | 5.6 |
| `static/js/admin.js` (new) | 5.6 |
| `templates/index.html` | 5.3 |
| `static/css/style.css` | 5.3 |
| `app/auth/routes.py` | 5.1, 5.3 |
| `app/routes/stream.py` | 5.4 |
| `app/routes/download.py` | 5.4 |
| `app/downloader.py` | 5.4 |
