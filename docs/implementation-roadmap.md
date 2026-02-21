# Zora — Implementation Roadmap

> **Reference:** `docs/auth-rbac-spec.md` (the what)  
> **This document:** the exact build order (the how)  
> **Last updated:** 2026-02-20  
> **Estimated total:** ~15–20 hours across 4 phases

---

## How To Read This

Each task has:
- **[ ]** checkbox — mark when done
- **Depends on** — what must be finished first
- **Files** — what you'll create or modify
- **Done when** — how to verify it works

---

## Phase 1 — Local Auth + RBAC + Playlist Ownership

> Goal: Login/signup works, roles enforced, playlists owned by users.  
> Estimate: ~8–10 hours

---

### Step 1.1 — Cleanup: Delete dead code

> Depends on: nothing  
> Effort: 5 minutes

- [x] Delete `server.py`
- [x] Delete `data.db` and `zora.db`
- [x] Delete `history.json` if it exists
- [x] Remove JSON migration code from `app/models/database.py` (`migrate_from_json`)
- [x] Remove JSON migration call from `app/__init__.py`

**Files:** `server.py` (delete), `data.db` (delete), `zora.db` (delete), `app/__init__.py`, `app/models/database.py`

**Done when:** `python run.py` starts cleanly with no errors, serves the app at localhost:5001.

---

### Step 1.2 — Split `routes/api.py` into focused files

> Depends on: 1.1  
> Effort: ~30 minutes

Split the ~800-line `routes/api.py` into:

- [x] `routes/api.py` — keep only `GET /` (index route)
- [x] `routes/download.py` — move `start_download`, `_background_download`, `get_status`, playlist-download endpoints, all download helpers
- [x] `routes/search.py` — move `get_info`, `search`, `get_playlist_items`
- [x] `routes/stream.py` — move `play_audio`, `serve_thumbnail`, `serve_download`
- [x] Update `routes/__init__.py` — register new blueprints
- [x] Update `app/__init__.py` — register new blueprints

**Files:** `app/routes/api.py`, `app/routes/download.py` (new), `app/routes/search.py` (new), `app/routes/stream.py` (new), `app/routes/__init__.py`, `app/__init__.py`

**Done when:** All existing functionality works exactly as before. Every API endpoint responds the same. Run the app → search → download → play → playlists → settings all work.

---

### Step 1.3 — Install new dependencies

> Depends on: nothing (can run in parallel with 1.1)  
> Effort: 2 minutes

- [x] Add to `requirements.txt`:
  ```
  Flask-Login>=0.6.0
  Flask-WTF>=1.2.0
  Flask-Limiter>=3.0.0
  ```
- [x] Run `pip install -r requirements.txt`

**Files:** `requirements.txt`

**Done when:** `python -c "import flask_login; import flask_wtf; import flask_limiter; print('OK')"` prints OK.

---

### Step 1.4 — Create User model

> Depends on: 1.3  
> Effort: ~20 minutes

- [x] Create `app/models/user.py` with User model (spec §5.1):
  - `id`, `name`, `email`, `password_hash`, `role`, `auth_provider`, `google_sub`, `avatar_url`, `is_active`, `email_verified`, `created_at`, `updated_at`, `last_login_at`
  - `set_password(plain)` method using `werkzeug.security.generate_password_hash`
  - `check_password(plain)` method using `werkzeug.security.check_password_hash`
  - `to_dict()` method (never expose `password_hash`)
  - `is_admin` property → `self.role == 'admin'`
  - Implement Flask-Login's `UserMixin` (provides `is_authenticated`, `is_active`, `get_id`)
- [x] Update `app/models/__init__.py` — export `User`
- [x] Add `owner_user_id` FK column to `Playlist` model in `app/models/playlist.py`
  - `owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)`
  - Remove global `unique=True` from `name` column
  - Update `to_dict()` to include `owner_user_id`

**Files:** `app/models/user.py` (new), `app/models/__init__.py`, `app/models/playlist.py`

**Done when:** App starts, `db.create_all()` creates `users` table alongside existing tables. Verify with `sqlite3 data.db ".tables"` showing `users` in the list.

---

### Step 1.5 — Create auth package (Flask-Login + decorators)

> Depends on: 1.4  
> Effort: ~45 minutes

- [x] Create `app/auth/__init__.py`:
  - `init_auth(app)` function that:
    - Creates `LoginManager` instance
    - Sets `login_manager.user_loader` to load User by ID
    - Sets `login_manager.unauthorized` to return JSON 401 (not redirect)
    - Calls `login_manager.init_app(app)`
- [x] Create `app/auth/decorators.py`:
  - `@admin_required` — wraps `@login_required` + checks `current_user.role == 'admin'`, returns 403 JSON if not
  - `@owns_playlist(param_name)` — checks `playlist.owner_user_id == current_user.id`, admin bypasses, returns 403 if not owner
- [x] Update `app/__init__.py`:
  - Call `init_auth(app)` in `create_app()`
  - CSRF deferred (WTF_CSRF_ENABLED=False); SameSite=Lax cookies + Content-Type check provide protection. Full CSRF → Phase 4.
  - Add session cookie config (httponly, samesite)
  - Set `SECRET_KEY` from env var (not random — must persist across restarts)

**Files:** `app/auth/__init__.py` (new), `app/auth/decorators.py` (new), `app/__init__.py`

**Done when:** App starts. Importing `from app.auth.decorators import admin_required, owns_playlist` works without errors.

---

### Step 1.6 — Admin bootstrap on startup

> Depends on: 1.5  
> Effort: ~15 minutes

- [x] In `app/__init__.py` `create_app()`, after `db.create_all()`:
  - Check if `User` table is empty
  - If empty AND `ZORA_ADMIN_EMAIL` + `ZORA_ADMIN_PASSWORD` env vars set:
    - Create admin user with `role='admin'`, `auth_provider='local'`, `email_verified=True`
    - Print `"✅ Admin account created for {email}"`
  - If empty AND env vars NOT set:
    - Print `"⚠️ No users exist and ZORA_ADMIN_EMAIL not set. Set env vars and restart."`
- [x] Update `.env` example in README

**Files:** `app/__init__.py`, `README.md`

**Done when:** Set `ZORA_ADMIN_EMAIL=admin@test.com` and `ZORA_ADMIN_PASSWORD=testpass123` in `.env`, delete `data.db`, run app → console shows admin created. `sqlite3 data.db "SELECT email, role FROM users"` shows the admin row.

---

### Step 1.7 — Create auth routes (signup, login, logout, me)

> Depends on: 1.6  
> Effort: ~1 hour

- [x] Create `app/auth/routes.py` with blueprint `auth`:
  - `POST /api/auth/signup`:
    - Accept `name`, `email`, `password`, `confirm_password`
    - Validate: email format, password min 8 chars, passwords match, email not taken
    - Normalize email (lowercase, strip)
    - Create user with `role='user'`, hash password
    - Auto-login after signup (Flask-Login `login_user()`)
    - Return user JSON
  - `POST /api/auth/login`:
    - Accept `email`, `password`
    - Find user by email, check password, check `is_active`
    - `login_user(user)`, update `last_login_at`
    - Return user JSON
  - `POST /api/auth/logout`:
    - `@login_required`
    - `logout_user()`
    - Return success
  - `GET /api/auth/me`:
    - `@login_required`
    - Return `current_user.to_dict()`
  - `POST /api/auth/password/change`:
    - `@login_required`
    - Accept `current_password`, `new_password`
    - Verify current, set new, invalidate other sessions
- [x] Register auth blueprint in `app/__init__.py`
- [x] Rate limiting deferred — Flask-Limiter installed but rate decorators not yet applied. Will tune in Phase 4.

**Files:** `app/auth/routes.py` (new), `app/__init__.py`

**Done when:** Using curl or Postman:
```bash
# Signup
curl -X POST localhost:5001/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","email":"test@test.com","password":"test1234","confirm_password":"test1234"}'

# Login
curl -X POST localhost:5001/api/auth/login -c cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"test1234"}'

# Me (should return user)
curl localhost:5001/api/auth/me -b cookies.txt

# Logout
curl -X POST localhost:5001/api/auth/logout -b cookies.txt
```

---

### Step 1.8 — Add default-deny middleware + route guards

> Depends on: 1.7  
> Effort: ~45 minutes

- [x] Add `@app.before_request` in `app/__init__.py`:
  - Allowlist public endpoints: `auth.signup`, `auth.login`, `auth.google_start`, `auth.google_callback`, `api.index`, `static`
  - Everything else requires `current_user.is_authenticated` → 401 JSON if not
- [x] Add `@admin_required` decorator to admin-only routes:
  - `routes/download.py` — all endpoints
  - `routes/search.py` — all endpoints
  - `routes/settings.py` — all endpoints
  - `routes/queue.py` — all endpoints
  - `routes/history.py` — `clear_history`, `delete_download`
  - `routes/stream.py` — `serve_download` (file download, NOT play)
- [x] Keep authenticated-only (no admin check) on:
  - `routes/history.py` — `get_history` (library browsing)
  - `routes/stream.py` — `play_audio` (streaming)
  - `routes/playlists.py` — all endpoints (with ownership check)
- [x] Add `@owns_playlist` to playlist routes:
  - `delete_playlist`, `get_playlist_songs`, `add_song_to_playlist`, `remove_song_from_playlist`
- [x] Update all playlist queries to filter by `owner_user_id = current_user.id`
- [x] On `POST /api/playlists` (create), set `owner_user_id = current_user.id`

**Files:** `app/__init__.py`, `app/routes/download.py`, `app/routes/search.py`, `app/routes/settings.py`, `app/routes/queue.py`, `app/routes/history.py`, `app/routes/stream.py`, `app/routes/playlists.py`

**Done when:**
```bash
# Guest → 401
curl localhost:5001/api/history  # → 401

# User → can read library, cannot download
curl localhost:5001/api/history -b user-cookies.txt     # → 200
curl -X POST localhost:5001/api/download -b user-cookies.txt  # → 403

# Admin → can do everything
curl -X POST localhost:5001/api/download -b admin-cookies.txt  # → 200
```

---

### Step 1.9 — Frontend: api.js auth support

> Depends on: 1.8  
> Effort: ~30 minutes

- [x] Update `static/js/api.js`:
  - Added `API._fetch()` wrapper with global 401→login redirect and 403→toast handling
  - Added `API._jsonOptions()` helper for JSON POST/PATCH/DELETE
  - Added `API.auth.login()`, `API.auth.signup()`, `API.auth.logout()`, `API.auth.me()`, `API.auth.changePassword()`
  - All existing API methods now route through `_fetch()` for consistent error handling
  - CSRF meta tag deferred — using SameSite=Lax cookies + JSON Content-Type for protection. Full CSRF → Phase 4.

**Files:** `static/js/api.js`, `templates/index.html`

**Done when:** Open browser dev console → `API.auth.me()` returns user object when logged in, triggers login redirect when not.

---

### Step 1.10 — Frontend: login/signup views + role-aware UI

> Depends on: 1.9  
> Effort: ~1.5 hours

- [x] Add login view in `templates/index.html` (SPA style, matching existing pattern):
  - Email + password fields, submit calls `handleLogin()`
  - Link to signup via `switchAuthTab('signup')`
  - Google button deferred to Phase 2
- [x] Add signup view:
  - Name + email + password + confirm password fields, submit calls `handleSignup()`
  - Link back to login
- [x] Update `static/js/app.js` `init()`:
  - On page load → calls `API.auth.me()`
  - If null → `showView('login')`, hide sidebar/nav/header
  - If user → store in `State.user`, boot full app, show library
- [x] Add `applyRoleUI()` for role-aware toggling:
  - `data-role="admin"` attribute on admin-only nav links, settings buttons
  - Sidebar, mobile-nav, mobile-header hidden when not logged in
  - Settings buttons hidden for user role
- [x] Add user avatar initial + name + role + logout button in sidebar footer (`#sidebarUserInfo`)
- [x] Add `showView('login')` and `showView('signup')` to view router
- [x] Add auth-card + sidebar-user CSS in `static/css/style.css`
- [x] Default view changed from download → library (accessible to all roles)
- [x] Mobile bottom nav updated: Download (admin-only), Library, Playlists

**Files:** `templates/index.html`, `static/js/app.js`, `static/js/ui.js`, `static/css/style.css`

**Done when:**
1. Open app → see login screen
2. Sign up → redirected to main app with user role → cannot see download/settings
3. Login as admin → can see everything
4. Logout → back to login screen

---

### Step 1.11 — CLI admin recovery tool

> Depends on: 1.6  
> Effort: ~15 minutes

- [x] Create `manage.py` with `reset-admin` command:
  ```bash
  python manage.py reset-admin
  ```
  - Reads `ZORA_ADMIN_EMAIL` and `ZORA_ADMIN_PASSWORD` from env (or `.env` file)
  - If user exists → reset password hash, set `is_active = True`, set `role = 'admin'`
  - If user doesn't exist → create admin account
  - Works without running the web server (direct DB access via app context)
  - Includes own `.env` loader (no python-dotenv dependency required at CLI level)

**Files:** `manage.py` (new)

**Done when:** `ZORA_ADMIN_EMAIL=admin@test.com ZORA_ADMIN_PASSWORD=newpass python manage.py reset-admin` succeeds, admin can login with new password.

---

### Step 1.12 — Phase 1 smoke test

> Depends on: all of 1.1–1.11  
> Effort: ~30 minutes

- [x] Automated smoke test passed (test_client: guest→401, admin login→200, admin access→200, logout→401, user signup→201, user library→200, user download→403)
- [x] Full test matrix verified (54 tests in `tests/test_auth_matrix.py` — all passed):

| Action | Guest | User | Admin |
|---|---|---|---|
| See login page | ✅ | — | — |
| Signup | ✅ | — | — |
| Login | ✅ | — | — |
| Browse library | ❌ 401 | ✅ | ✅ |
| Stream/play song | ❌ 401 | ✅ | ✅ |
| Create playlist | ❌ 401 | ✅ (own) | ✅ (own) |
| See other user's playlists | ❌ 401 | ❌ 403 | ❌ 403 |
| Search YouTube | ❌ 401 | ❌ 403 | ✅ |
| Download song | ❌ 401 | ❌ 403 | ✅ |
| Change settings | ❌ 401 | ❌ 403 | ✅ |
| Delete song from library | ❌ 401 | ❌ 403 | ✅ |
| Clear history | ❌ 401 | ❌ 403 | ✅ |
| Manage queue | ❌ 401 | ❌ 403 | ✅ |
| Logout | — | ✅ | ✅ |

- [x] Verify no endpoint is accidentally left unguarded
- [x] Verify playlist isolation (user A can't see user B's playlists)

**Done when:** Every cell in the matrix matches expected behavior.

---

## Phase 2 — Google OAuth

> Goal: "Continue with Google" works for login and signup.  
> Depends on: Phase 1 complete  
> Estimate: ~3–4 hours

---

### Step 2.1 — Install Authlib

- [x] Add `authlib>=1.3.0` to `requirements.txt`
- [x] `pip install -r requirements.txt`
- [x] Added `requests>=2.31.0` (required dependency of authlib)

---

### Step 2.2 — Google OAuth backend

- [x] Create `app/auth/google.py`:
  - Configure OAuth client with `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
  - `GET /api/auth/google/start` → redirect to Google consent screen
  - `GET /api/auth/google/callback` → handle callback:
    - Verify `state` param (handled by Authlib)
    - Get user info from Google (email, name, sub, picture)
    - Apply account linking policy (spec §3.3):
      - No account → create `user`, `auth_provider=google`
      - Existing local account same email → link, set `auth_provider=hybrid`
      - Account deactivated → reject
    - `login_user()`, update `last_login_at`
    - Redirect to `/`
- [x] Register Google auth routes in `app/auth/__init__.py` + `app/__init__.py` (blueprint `google_auth`)
- [x] CSRF not applicable (CSRF is disabled in Phase 1; Google callback uses GET + state param)
- [x] Add Google OAuth endpoints to public allowlist in `before_request` (`google_auth.google_start`, `google_auth.google_callback`)

**Files:** `app/auth/google.py` (new), `app/auth/__init__.py`, `app/__init__.py`

---

### Step 2.3 — Google OAuth frontend

- [x] Add "Continue with Google" button to login and signup views
  - Links to `/api/auth/google/start`
  - Styled with Google brand guidelines (white button, Google G logo SVG, `.btn--google`)
  - Added `.auth-divider` ("or") separator between form and Google button
- [x] Handle redirect back from Google (page loads → `GET /api/auth/me` → show main app)
- [x] Added OAuth error handling in `app.js` — reads `?error=` query param, shows toast, cleans URL

**Files:** `templates/index.html`, `static/css/style.css`

---

### Step 2.4 — Phase 2 smoke test

- [x] Click "Continue with Google" → redirects to Google → authorizes → redirected back → logged in
- [x] Google account with no existing Zora account → new `user` created (verified in `tests/test_google_oauth.py`)
- [x] Google account with same email as existing local account → accounts linked, `auth_provider=hybrid`
- [x] Deactivated account tries Google login → rejected with `?error=account_disabled`
- [x] Login state persists across page refreshes (verified: 3 sequential `/api/auth/me` calls all return 200)
- [x] Unverified Google email → rejected with `?error=google_email_not_verified`
- [x] 10 tests in `tests/test_google_oauth.py` — all passed

---

## Phase 3 — Admin Panel + Audit Logs

> Goal: Admin can manage users and see audit trail.  
> Depends on: Phase 1 complete (Phase 2 optional)  
> Estimate: ~3–4 hours

---

### Step 3.1 — Audit log model

- [x] Create `app/models/audit_log.py` with AuditLog model (spec §5.2)
  - Columns: `id`, `actor_user_id` (FK), `action`, `target_type`, `target_id`, `metadata_json`, `ip_address`, `user_agent`, `created_at`
  - `to_dict()` method with actor name/email resolution
  - Relationship to `User` model via `actor` backref
- [x] Create `log_action(action, target_type, target_id, metadata, user)` helper
  - Auto-captures `current_user`, IP address, and user agent from request context
- [x] Update `app/models/__init__.py` — export `AuditLog` and `log_action`

**Files:** `app/models/audit_log.py` (new), `app/models/__init__.py`

---

### Step 3.2 — Add audit logging to admin actions

- [x] Add `log_action()` calls to:
  - `POST /api/download` → `DOWNLOAD_CREATE` (with url, format, quality metadata)
  - `POST /api/settings` → `SETTINGS_UPDATE` (with changed settings metadata)
  - `POST /api/history/clear` → `HISTORY_CLEAR`
  - `POST /api/history/delete/<id>` → `SONG_DELETE` (with title, filename metadata)
  - `PATCH /api/admin/users/<id>` → `USER_ROLE_CHANGE` or `USER_DEACTIVATE`/`USER_ACTIVATE`

**Files:** `app/routes/download.py`, `app/routes/settings.py`, `app/routes/history.py`, `app/admin/routes.py`

---

### Step 3.3 — Admin API routes

- [x] Create `app/admin/__init__.py`
- [x] Create `app/admin/routes.py` with blueprint `admin`:
  - `GET /api/admin/users` — list all users (paginated, searchable by name/email)
  - `GET /api/admin/users/<id>` — single user detail
  - `PATCH /api/admin/users/<id>` — update role, activate/deactivate
    - Prevent last-admin demotion (409)
    - Prevent self-deactivation (409)
    - Log action to audit_logs
  - `GET /api/admin/audit-logs` — list audit logs (paginated, filterable by action/user)
- [x] All routes decorated with `@admin_required`
- [x] Register admin blueprint in `app/__init__.py` with `url_prefix='/api/admin'`

**Files:** `app/admin/__init__.py` (new), `app/admin/routes.py` (new), `app/__init__.py`

---

### Step 3.4 — Admin panel frontend

- [x] Add "Admin" nav link in sidebar (visible only for admin role, `data-role="admin"`)
- [x] Add admin panel view with:
  - Users table: name (with avatar), email, role, status (active/inactive), created date, last login
  - Search/filter bar with debounced search
  - Role dropdown per user (admin/user), disabled for self
  - Activate/deactivate toggle per user
  - Pagination
- [x] Add audit log view (sub-tab of admin panel):
  - Table: timestamp, actor name, action, target, details, IP
  - Filter by action type (dropdown)
  - Pagination
- [x] Add `API.admin.getUsers()`, `API.admin.updateUser()`, `API.admin.getAuditLogs()` to `api.js`
- [x] Responsive: hides Created/Last Login columns on mobile

**Files:** `templates/index.html`, `static/js/app.js`, `static/js/api.js`, `static/css/style.css`

---

### Step 3.5 — Phase 3 smoke test

- [x] Admin sees admin panel, user does not (tested: `data-role="admin"` + `@admin_required`)
- [x] Admin can change user's role → reflected immediately (tested: 19 admin tests pass)
- [x] Admin cannot demote the last admin → error shown (tested: returns 409)
- [x] Admin can deactivate a user → that user can't login (tested: `is_active=False`)
- [x] Audit logs show all admin actions with correct details (tested: logs with actor info, metadata)
- [x] 19 new tests in `tests/test_admin.py` — all passed, total suite: 109 tests passing

---

## Phase 4 — Password Reset + Security Hardening

> Goal: Users can recover accounts, security is production-grade.  
> Depends on: Phase 1 complete  
> Estimate: ~2–3 hours

---

### Step 4.1 — Password reset (requires SMTP)

- [x] Add `password_reset_tokens` table (spec §5.4)
  - Created `app/models/password_reset.py` with `PasswordResetToken` model
  - `hash_token()`, `create_for_user()`, `validate_token()` class methods
  - Token hashed with SHA-256 before storage, plain token sent in email
- [x] Add env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ZORA_BASE_URL`
- [x] `POST /api/auth/password/reset/request` → generate token, send email
  - Returns generic success message to prevent email enumeration
  - Google-only accounts silently skipped
  - Falls back to console logging when SMTP not configured
- [x] `POST /api/auth/password/reset/confirm` → verify token, update password
  - Validates token, enforces min 8-char password, marks token as used
  - Logs `PASSWORD_RESET` audit action
- [x] Add "Forgot password?" link on login view
  - Added forgot-password view with email input
  - Added reset-password view with new password + confirm fields
  - Auto-detects `?reset_token=` URL param and shows reset view
- [x] Token expires in 1 hour, single-use
  - New token invalidates all previous unused tokens for that user
- [x] Both reset endpoints added to public allowlist in `before_request`

**Files:** `app/models/password_reset.py` (new), `app/models/__init__.py`, `app/auth/routes.py`, `app/__init__.py`, `templates/index.html`, `static/js/api.js`, `static/js/app.js`, `static/css/style.css`

---

### Step 4.2 — Security headers middleware

- [x] Add `@app.after_request` with:
  ```
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  X-XSS-Protection: 1; mode=block
  Referrer-Policy: strict-origin-when-cross-origin
  ```

**Files:** `app/__init__.py`

---

### Step 4.3 — Rate limiting tuning

- [x] Created shared `app/limiter.py` with Flask-Limiter instance
- [x] Initialized in `create_app()`, auto-disabled when `TESTING=True`
- [x] Applied rate limits to sensitive endpoints:
  - `login`: 5 per minute
  - `signup`: 3 per minute
  - `change_password`: 3 per minute
  - `request_password_reset`: 3 per minute
  - `confirm_password_reset`: 5 per minute
  - `update_user` (admin): 10 per minute

**Files:** `app/limiter.py` (new), `app/__init__.py`, `app/auth/routes.py`, `app/admin/routes.py`

---

### Step 4.4 — Final security checklist

- [x] Passwords hashed with werkzeug (PBKDF2), never stored plain text
- [x] Rate limiting on login, signup, password reset, password change, admin actions
- [x] CSRF protection via SameSite=Lax cookies + JSON Content-Type check
- [x] Email input validated and normalized (lowercase, trimmed)
- [x] Server-side role checks on every protected route (default-deny middleware)
- [x] Session cookie: HttpOnly, SameSite=Lax, Secure in production
- [x] Google OAuth `state` parameter validated (handled by Authlib)
- [x] `SECRET_KEY` loaded from env var, not default random
- [x] Security headers: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy
- [x] Admin actions recorded in audit_logs
- [x] No secrets in client-side code or API responses (password_hash never exposed)
- [x] Deactivated users fully locked out (login + Google OAuth + password reset all check is_active)
- [x] 24 new tests in `tests/test_password_reset.py` — all passed, total suite: 133 tests passing

---

## Dependency Graph

```
Phase 1 (must be sequential internally):
  1.1 Cleanup ──→ 1.2 Split api.py ──→ 1.4 User model ──→ 1.5 Auth package
       │                                                         │
       └── 1.3 Install deps (parallel) ─────────────────────────┘
                                                                 │
                                              1.6 Admin bootstrap
                                                                 │
                                              1.7 Auth routes ───┤
                                                                 │
                                              1.8 Route guards ──┤
                                                                 │
                                              1.9 api.js auth ───┤
                                                                 │
                                              1.10 Frontend UI ──┤
                                                                 │
                                              1.11 CLI tool       │
                                                                 │
                                              1.12 Smoke test ◄──┘

Phase 2 (after Phase 1):   2.1 → 2.2 → 2.3 → 2.4
Phase 3 (after Phase 1):   3.1 → 3.2 → 3.3 → 3.4 → 3.5
Phase 4 (after Phase 1):   4.1 → 4.2 → 4.3 → 4.4

Phases 2, 3, 4 are independent of each other — can be built in any order.
```

---

## Final File Tree After All Phases

```
zora/
├── app/
│   ├── __init__.py              ← MODIFIED (auth init, CSRF, before_request, admin bootstrap)
│   ├── auth/                    ← NEW PACKAGE
│   │   ├── __init__.py          ← Flask-Login setup, user_loader
│   │   ├── decorators.py        ← @admin_required, @owns_playlist
│   │   ├── routes.py            ← login, signup, logout, me, password change, password reset (Phase 4)
│   │   └── google.py            ← Google OAuth (Phase 2)
│   ├── admin/                   ← NEW PACKAGE (Phase 3)
│   │   ├── __init__.py
│   │   └── routes.py            ← user management, audit log viewing
│   ├── models/
│   │   ├── __init__.py          ← MODIFIED (export User, AuditLog)
│   │   ├── database.py          ← MODIFIED (remove migrate_from_json)
│   │   ├── user.py              ← NEW
│   │   ├── audit_log.py         ← NEW (Phase 3)
│   │   ├── password_reset.py    ← NEW (Phase 4)
│   │   ├── download.py          ← unchanged
│   │   ├── playlist.py          ← MODIFIED (add owner_user_id)
│   │   └── settings.py          ← unchanged
│   ├── routes/
│   │   ├── __init__.py          ← MODIFIED (register new blueprints)
│   │   ├── api.py               ← MODIFIED (only GET / index)
│   │   ├── download.py          ← NEW (split from api.py)
│   │   ├── search.py            ← NEW (split from api.py)
│   │   ├── stream.py            ← NEW (split from api.py)
│   │   ├── history.py           ← MODIFIED (add decorators)
│   │   ├── playlists.py         ← MODIFIED (add decorators + ownership)
│   │   ├── settings.py          ← MODIFIED (add @admin_required)
│   │   └── queue.py             ← MODIFIED (add @admin_required)
│   ├── services/                ← unchanged
│   ├── downloader.py            ← unchanged
│   ├── limiter.py               ← NEW (Phase 4 — shared Flask-Limiter instance)
│   ├── exceptions.py            ← unchanged
│   ├── utils.py                 ← unchanged
│   └── ...
├── static/
│   ├── js/
│   │   ├── api.js               ← MODIFIED (CSRF, auth methods, 401/403 handling)
│   │   ├── app.js               ← MODIFIED (auth flow, role-aware UI, login/signup views)
│   │   ├── player.js            ← unchanged
│   │   └── ui.js                ← MODIFIED (role-aware element toggling)
│   └── css/
│       └── style.css            ← MODIFIED (login/signup/admin panel styles)
├── templates/
│   └── index.html               ← MODIFIED (CSRF meta, login/signup views, admin panel)
├── docs/
│   ├── auth-rbac-spec.md        ← reference spec
│   └── implementation-roadmap.md ← this file
├── manage.py                    ← NEW (admin recovery CLI)
├── run.py                       ← unchanged
├── main.py                      ← unchanged
├── requirements.txt             ← MODIFIED
├── .env                         ← MODIFIED (add admin + Google vars)
└── README.md                    ← MODIFIED (auth docs)

DELETED: server.py, data.db, zora.db, history.json
```
