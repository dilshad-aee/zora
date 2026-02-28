# Zora — Known Issues & Improvement Plan

> Audit date: Feb 24, 2026  
> Scope: Auth/session, playlist controls, playlist UI/UX, music slider  
> **Status: All 11 issues FIXED ✅**

---

## Table of Contents

| # | Issue | Severity |
|---|-------|----------|
| 1 | [Session expires — forced re-login](#1-session-expires--forced-re-login) | 🔴 Critical |
| 2 | [Swipe left/right navigates to login page](#2-swipe-leftright-navigates-to-login-page) | 🔴 Critical |
| 3 | [Service Worker caches stale API auth state](#3-service-worker-caches-stale-api-auth-state) | 🟠 High |
| 4 | [Music slider hijacked by global gesture system](#4-music-slider-hijacked-by-global-gesture-system) | 🔴 Critical |
| 5 | [Music slider lacks drag-to-seek (not industry standard)](#5-music-slider-lacks-drag-to-seek-not-industry-standard) | 🟠 High |
| 6 | [Now Playing progress bar missing touch-action isolation](#6-now-playing-progress-bar-missing-touch-action-isolation) | 🟠 High |
| 7 | [Play All vs Shuffle confusion](#7-play-all-vs-shuffle-confusion) | 🟡 Medium |
| 8 | [Loop button behaviour is unclear](#8-loop-button-behaviour-is-unclear) | 🟡 Medium |
| 9 | [Playlist controls state not synced with player bar](#9-playlist-controls-state-not-synced-with-player-bar) | 🟡 Medium |
| 10 | [Newly created playlists sometimes don't appear](#10-newly-created-playlists-sometimes-dont-appear) | 🟠 High |
| 11 | [Playlist detail UI/UX improvements](#11-playlist-detail-uiux-improvements) | 🟡 Medium |

---

## 1. Session expires — forced re-login

### Symptom
User opens the app (or returns after the device sleeps) and is sent back to the login page despite having logged in previously.

### Root Cause
**Flask-Login's `login_user()` is called without `remember=True`.**

```python
# app/auth/routes.py  — lines 58, 90
login_user(user)          # ← no remember=True
```

Without `remember=True`, Flask-Login uses a **session cookie** (no `Expires`/`Max-Age`), which lives only as long as the browser tab or app is open. On mobile (PWA, Safari, Chrome) the OS reclaims memory aggressively, the session cookie is lost, and the user must re-login.

Additionally, **`PERMANENT_SESSION_LIFETIME` is never configured** (defaults to 31 days but only matters if `session.permanent = True`, which is never set). And `REMEMBER_COOKIE_DURATION` is never set either.

### Files involved
| File | Line(s) | Problem |
|------|---------|---------|
| `app/auth/routes.py` | 58, 90 | `login_user(user)` missing `remember=True` |
| `app/auth/google.py` | 122 | Same issue for Google OAuth login |
| `app/auth/__init__.py` | 11-18 | No `REMEMBER_COOKIE` config |
| `app/__init__.py` | 53-60 | No `PERMANENT_SESSION_LIFETIME` or `REMEMBER_COOKIE_DURATION` |
| `config/__init__.py` | 24 | `SECRET_KEY` uses `os.urandom(24).hex()` — changes on every restart, invalidating all sessions |

### Fix required
1. Change all `login_user(user)` → `login_user(user, remember=True)`
2. Set `REMEMBER_COOKIE_DURATION = timedelta(days=30)` in app config
3. Set `REMEMBER_COOKIE_HTTPONLY = True`, `REMEMBER_COOKIE_SAMESITE = 'Lax'`
4. Fix `SECRET_KEY` — the current fallback generates a new random key on every server restart, which invalidates **all** existing session cookies immediately. Must be a stable env var or persisted value.

---

## 2. Swipe left/right navigates to login page

### Symptom
While browsing any view, a horizontal swipe gesture causes the user to land on the login page, even though they are authenticated.

### Root Cause
**Two problems combine to cause this:**

**Problem A — Global gesture handler on `document`:**  
`player.js` → `setupGestureControls()` (line 289) attaches `touchstart`/`touchend` listeners to the **entire `document`**. Any horizontal swipe (deltaX > 50, deltaY < 30, time < 300ms) triggers `skipForward(10)` or `skipBackward(10)`. This fires even when:
- The user is scrolling a horizontally-scrollable element (category pills, playlist tabs)
- The user is swiping between views on mobile
- No song is playing

These events do NOT prevent default — the browser still processes the swipe as a native back/forward navigation (iOS Safari "swipe to go back").

**Problem B — API 401 handler fires as a side-effect:**  
`api.js` → `_fetch()` (line 14) treats **any** 401 response by calling `showView('login')`. If the service worker serves a cached 401 response, or a background API call hits an expired session, the user is silently dumped to the login page.

### Files involved
| File | Line(s) | Problem |
|------|---------|---------|
| `static/js/player.js` | 289-368 | `setupGestureControls()` binds to `document` globally with no target filtering |
| `static/js/player.js` | 316 | Swipe threshold too low (50px), no check for active player or target element |
| `static/js/api.js` | 14-17 | 401 handler calls `showView('login')` — fires on cached responses too |

### Fix required
1. **Restrict gesture listeners** to only fire when the swipe originates inside the player bar or now-playing panel (`e.target.closest('.player, .now-playing')`)
2. Add `e.preventDefault()` + `e.stopPropagation()` when the gesture is consumed
3. Add a guard: only process gestures if `Player.currentTrack` is not null
4. In `_fetch()` 401 handler: check if `State.user` was already set (i.e., the user was logged in) and show a re-login toast instead of silently switching views

---

## 3. Service Worker caches stale API auth state

### Symptom
After the session cookie expires, the SW may serve cached API responses (from `zora-api-*` cache) that return 401/stale data, triggering the 401 → login-page cascade.

### Root Cause
`sw.js` line 97 uses `networkFirst()` for all GET `/api/*` requests. When the network request succeeds **with a 401**, it is NOT cached (only `response.ok` is cached). However, the timeout fallback (line 144) will serve an old cached response that may include stale auth state or, worse, a cached 401 from a previous failure.

The `/api/auth/me` endpoint is **not excluded** from service worker caching and is not in `PUBLIC_ENDPOINTS` — so it can return a cached "authenticated" response even when the session is gone, or a cached 401 that triggers re-login.

### Files involved
| File | Line(s) | Problem |
|------|---------|---------|
| `static/sw.js` | 78-98 | All GET `/api/*` routes go through cache — including auth endpoints |
| `static/sw.js` | 130-153 | `networkFirst()` caches 200 responses; on timeout it may serve stale cached data |

### Fix required
1. Exclude `/api/auth/me` from service worker caching (always network-only)
2. Exclude all `/api/auth/*` routes from caching
3. On 401 responses, **delete** the cached entry for that URL so stale data doesn't persist
4. Consider adding a `Cache-Control: no-store` header to auth responses server-side

---

## 4. Music slider hijacked by global gesture system

### Symptom
When the user tries to drag/scrub the music progress bar (either in the bottom player bar or in the Now Playing panel), the gesture is intercepted by the global swipe handler, causing the audio to skip forward/backward 10 seconds instead of seeking to the desired position.

### Root Cause
`player.js` → `setupGestureControls()` (line 295) filters out touches on `.player__progress-bar` and `.now-playing__progress-bar` in `touchstart`, but the corresponding `touchend` handler (line 306) does **NOT** have the same filter. So:

1. User touches the progress bar → `touchstart` returns early (correct)
2. But `touchStartX`/`touchStartY` were set from a **previous** touch event
3. `touchend` fires → delta calculation uses the stale `touchStartX` → false swipe detected → `skipForward(10)` fires

Additionally, the **double-tap handler** (line 337) is also on `document` with no target filtering. Double-tapping anywhere (including on the progress bar to quickly seek) triggers `Player.toggle()` (play/pause).

### Files involved
| File | Line(s) | Problem |
|------|---------|---------|
| `static/js/player.js` | 295-298 | `touchstart` filter correct but incomplete |
| `static/js/player.js` | 306-326 | `touchend` swipe handler has NO target filter — processes all touch ends |
| `static/js/player.js` | 337-349 | Double-tap handler on `document` — no target filter at all |
| `static/js/player.js` | 353-361 | Long-press handler on `document` |

### Fix required
1. Add a `_gestureActive` flag set in `touchstart` — only process `touchend` if the flag is true
2. In `touchstart`: skip AND reset the flag for progress bars, sliders, buttons, modals, forms, and scrollable containers
3. Add target filtering to the double-tap handler — only trigger on the player area
4. Better: refactor all gesture listeners to bind to `.player` and `.now-playing` elements only, not `document`

---

## 5. Music slider lacks drag-to-seek (not industry standard)

### Symptom
The progress bar only supports **click/tap to seek** — there is no drag-to-scrub behaviour. Users expect to touch the handle and drag it continuously (like Spotify, Apple Music, YouTube Music).

### Root Cause
Both progress bars (`playerProgressBar` and `nowPlayingProgressBar`) only bind `click` and `touchstart` events (player.js lines 1247-1261). There is **no `touchmove`** or `mousemove` tracking for continuous seeking. The handle element exists in CSS (`.player__progress-handle`) but is purely decorative — it has `pointer-events: none` and isn't positioned dynamically during drag.

**Missing features compared to industry standard:**

| Feature | Spotify/Apple Music | Zora |
|---------|-------------------|------|
| Tap to seek | ✅ | ✅ |
| Drag handle to scrub | ✅ | ❌ |
| Handle follows finger during drag | ✅ | ❌ |
| Time preview while dragging | ✅ | ❌ |
| Enlarged hit area on touch | ✅ | ❌ (6px bar) |
| Buffered range indicator | ✅ | ❌ |
| Handle visible on hover/touch | ✅ | ✅ (CSS only) |

### Files involved
| File | Line(s) | Problem |
|------|---------|---------|
| `static/js/player.js` | 1254-1261 | Only `click` + `touchstart` — no `touchmove`/`mousemove` drag |
| `static/js/player.js` | 1244-1251 | Same for Now Playing bar |
| `static/js/player.js` | 601-618 | `seek()` method is single-shot, not continuous |
| `static/css/style.css` | 1940-1991 | Progress bar is only 6px tall; handle is CSS-only with no JS positioning |
| `static/css/style.css` | 2230-2248 | Now Playing bar is only 4px tall; no handle at all |

### Fix required
Implement a proper drag-to-seek system:

1. **`touchstart` / `mousedown`** on the progress bar:
   - Set a `_isDragging = true` flag
   - Add `.dragging` class to the bar
   - Call `e.preventDefault()` to prevent page scroll
   - Start tracking position

2. **`touchmove` / `mousemove`** (on `document` while dragging):
   - Calculate seek position relative to the bar
   - Update the fill width and handle position in real-time
   - Show a time tooltip above the handle
   - Do NOT update `audio.currentTime` yet (prevents audio stuttering)

3. **`touchend` / `mouseup`** (on `document`):
   - Commit the seek: `audio.currentTime = dragPosition * audio.duration`
   - Remove `.dragging` class
   - Reset `_isDragging = false`

4. **CSS improvements:**
   - Increase touch target to 44px (Apple HIG minimum) using a transparent pseudo-element
   - Show handle on touch (`pointer: coarse`) always, not just hover
   - Add buffered range indicator (second fill bar with lower opacity)
   - Add time tooltip positioned above the handle during drag

---

## 6. Now Playing progress bar missing touch-action isolation

### Symptom
Trying to scrub in the Now Playing fullscreen panel causes the panel to scroll or triggers the gesture system instead of seeking.

### Root Cause
The Now Playing progress bar (`.now-playing__progress-bar`) does NOT have `touch-action: none` in CSS. The bottom player bar has it (style.css line 1946), but the Now Playing bar does not (lines 2230-2236). This means the browser's default touch handling (scroll, pan) competes with the seek touch handler.

### Files involved
| File | Line(s) | Problem |
|------|---------|---------|
| `static/css/style.css` | 2230-2236 | `.now-playing__progress-bar` missing `touch-action: none` |
| `static/js/player.js` | 1248-1251 | `touchstart` uses `{ passive: false }` but CSS doesn't block default gestures |

### Fix required
Add `touch-action: none;` to `.now-playing__progress-bar` in CSS.

---

## 7. Play All vs Shuffle confusion

### Symptom
Users don't understand the difference between "Play All" and "Shuffle". Both buttons start playback. Pressing Shuffle after Play All doesn't reshuffle — it starts a new shuffled session. The active state isn't clear.

### Root Cause

1. **"Play All" doesn't disable shuffle** — if shuffle was previously enabled (from a prior session or the Now Playing panel), pressing "Play All" still plays in shuffled order because `Player.shuffle` remains `true`. The `playSelectedPlaylist(false)` only passes `shuffleStart=false` but does not call `setShuffleMode(false)`. (playlists.js line 904-922)

2. **"Shuffle" sets shuffle mode AND picks a random start index** — but if you later press "Play All", shuffle stays on. There's no toggle behaviour — both buttons are fire-and-forget.

3. **No visual indication of current mode** — the Shuffle button gets an `.active` class (playlists.js line 929) but only when pressed directly. If shuffle was already on from the player bar, the playlist Shuffle button doesn't reflect it.

4. **Play All icon and label are confusing** — "Play All" with a play icon looks the same as the main play button. Users expect "Play All" to play sequentially, but it may play shuffled.

### Files involved
| File | Line(s) | Problem |
|------|---------|---------|
| `static/js/playlists.js` | 904-922 | `playSelectedPlaylist()` doesn't force shuffle OFF when `shuffleStart=false` |
| `static/js/playlists.js` | 924-930 | `setShuffleMode()` only updates state, doesn't sync playlist button |
| `static/js/playlists.js` | 892-901 | `updatePlaylistPlaybackControls()` only enables/disables, doesn't sync active state |

### Fix required
1. `playSelectedPlaylist(false)` should call `setShuffleMode(false)` explicitly — "Play All" ALWAYS means sequential
2. `playSelectedPlaylist(true)` should call `setShuffleMode(true)` — "Shuffle" ALWAYS means shuffled
3. `updatePlaylistPlaybackControls()` should sync the active state from `Player.shuffle` and `Player.repeat`
4. Rename "Play All" to "▶ Play" and "Shuffle" to "🔀 Shuffle" with a toggle indicator

---

## 8. Loop button behaviour is unclear

### Symptom
The Loop button cycles through three states (Off → All → One) with a text label, but:
- Users don't understand what "Loop: All" vs "Loop: One" means
- There's no icon differentiation (same `fa-repeat` icon for all states)
- The button text truncates on mobile (grid becomes 2-col, Loop spans full width)

### Root Cause
`togglePlaylistLoop()` (playlists.js line 947-961) cycles `Player.repeat` through `['off', 'all', 'one']` and updates the button text. But:

1. No distinct icons per state (e.g., Spotify uses repeat icon, repeat icon highlighted, repeat-one icon)
2. The text "Loop: Off / All / One" is verbose and non-standard — streaming apps use icon-only toggle buttons
3. Button state doesn't sync on playlist open — if repeat was set via the player bar, the playlist Loop button doesn't reflect it

### Files involved
| File | Line(s) | Problem |
|------|---------|---------|
| `static/js/playlists.js` | 947-961 | `togglePlaylistLoop()` uses text labels instead of icon states |
| `static/js/playlists.js` | 892-901 | `updatePlaylistPlaybackControls()` doesn't sync loop state |
| `templates/index.html` | 559-562 | Loop button HTML has verbose default text |

### Fix required
1. Use icon-only states: `fa-repeat` (off/dim), `fa-repeat` (active/green), `fa-repeat` + "1" badge (repeat one)
2. Add tooltips for accessibility
3. Sync state from `Player.repeat` when the detail view opens
4. Match the pattern used in the Now Playing panel (`updateNowPlayingButtons()` at player.js line 1714-1721)

---

## 9. Playlist controls state not synced with player bar

### Symptom
The Shuffle/Loop buttons in the playlist detail view and the Shuffle/Repeat buttons in the player bar / Now Playing panel operate independently. Toggling shuffle in the player bar does NOT update the playlist view's Shuffle button, and vice versa.

### Root Cause
Each control updates `Player.shuffle` / `Player.repeat` state, but there's no unified event system. The playlist buttons update their own DOM directly (playlists.js lines 924-930, 947-961), and the player bar buttons update different DOM elements (player.js lines 1143-1153). Neither notifies the other.

### Files involved
| File | Problem |
|------|---------|
| `static/js/playlists.js` | Playlist buttons update their own DOM only |
| `static/js/player.js` | Player bar buttons update their own DOM only |
| No event bus or state observer exists | |

### Fix required
1. After any shuffle/repeat change, call a single `syncAllPlaybackModeUI()` function
2. This function updates: player bar buttons, now-playing buttons, AND playlist detail buttons
3. Alternatively, use `Player.updateShuffleButton()` / `Player.updateRepeatButton()` as the single source of truth and have playlist UI read from it

---

## 10. Newly created playlists sometimes don't appear

### Symptom
After creating a playlist (via the modal), the new playlist doesn't show in the "My Playlists" grid. The user must manually switch tabs or refresh.

### Root Cause
Multiple issues:

1. **`createPlaylistFromModal()` calls `createPlaylist()`** (playlists.js line 888), which calls `loadMyPlaylists()` — but `loadMyPlaylists()` re-fetches from the API and renders to `myPlaylistsGrid`. If the user is on the "Explore" tab, the "My Playlists" grid is hidden and the render happens to a hidden container. When they switch to "My Playlists" tab, `switchPlaylistTab('mine')` calls `loadMyPlaylists()` again — this should work, but…

2. **Service Worker caches the playlist list response.** `GET /api/playlists` goes through `networkFirst()` with a 10-second timeout. If the network response is slow (e.g., mobile), the SW may serve a **cached** response that doesn't include the newly created playlist.

3. **`State.playlists` has TWO list properties** — `State.playlists.items` (set in auth.js logout, line 133) and `State.playlists.list` (set in `loadMyPlaylists`, playlists.js line 134). The `items` property is never populated after login. Some code paths may check `items` instead of `list`.

4. **Race condition in `createPlaylistFromModal()`** (playlists.js lines 530-565 in the modal handler) — the modal's own create function may bypass the standard `createPlaylist()` flow and not call `loadMyPlaylists()`.

### Files involved
| File | Line(s) | Problem |
|------|---------|---------|
| `static/js/playlists.js` | 131-138 | `loadMyPlaylists()` stores to `State.playlists.list` |
| `static/js/auth.js` | 133 | Logout clears `State.playlists.items` (different property) |
| `static/sw.js` | 78-98 | Playlist GET may serve cached stale data |
| `static/js/playlists.js` | 870-886 | `createPlaylist()` relies on `loadMyPlaylists()` which may race with SW cache |

### Fix required
1. After `API.createPlaylist()` succeeds, **push the returned playlist directly into `State.playlists.list`** instead of re-fetching
2. Unify `State.playlists.items` and `State.playlists.list` — pick one and remove the other
3. Add `Cache-Control: no-cache` header to `GET /api/playlists` so the SW always revalidates
4. After creating a playlist, if user is on "Explore" tab, auto-switch to "My Playlists" tab

---

## 11. Playlist detail UI/UX improvements

### Current problems

| Issue | Detail |
|-------|--------|
| **No cover art** | Playlist card and detail show a generic `fa-compact-disc` icon. Could show a mosaic of first 4 song thumbnails |
| **No song count in detail header** | Song count is shown but doesn't update after adding/removing songs until a full reload |
| **Action buttons cramped on mobile** | "Add Songs", "Edit", "Delete" buttons wrap awkwardly on small screens |
| **No drag-to-reorder** | Users can't reorder songs within a playlist |
| **No song duration** | Song rows show title/artist but not duration |
| **No total playlist duration** | Header doesn't show total playtime |
| **Currently-playing highlight is subtle** | The `.playing` class only changes the number to a speaker icon; no background or border highlight |
| **Context menu positioning** | The 3-dot menu (`song-ctx-menu`) is positioned relative to the button parent but can overflow off-screen on mobile |

### Files involved
| File | Problem |
|------|---------|
| `static/js/playlists.js` | `renderPlaylistDetailHeader()`, `renderPlaylistDetailSongs()` |
| `static/css/style.css` | `.playlist-detail__*`, `.playlist-song-row` styles |
| `templates/index.html` | Playlist detail tab structure (lines 540-572) |

### Fix required (prioritized)
1. **P1:** Add song duration display and total playlist duration in header
2. **P1:** Better playing-now highlight (accent border-left + subtle background)
3. **P2:** Auto-composite album art from first 4 songs as playlist cover
4. **P2:** Improve mobile layout for owner action buttons (use icon-only on small screens)
5. **P3:** Drag-to-reorder with position persistence
6. **P3:** Context menu position clamping to viewport

---

## Summary: Priority order for fixes

| Priority | Issue(s) | Impact |
|----------|----------|--------|
| 🔴 **P0** | #1 (session), #2 (swipe-to-login), #4 (slider hijack) | App is unusable for mobile users |
| 🟠 **P1** | #3 (SW cache), #5 (drag-to-seek slider), #6 (NP touch-action), #10 (playlist not showing) | Core functionality broken or substandard |
| 🟡 **P2** | #7 (play/shuffle), #8 (loop button), #9 (state sync), #11 (playlist UI) | UX confusion, polish issues |
