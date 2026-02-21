# Zora — Authentication, Roles & Access Control Specification

> **Status:** Draft v2 — refined and ready for implementation  
> **Last updated:** 2026-02-17  
> **Scope:** Login, signup, Google OAuth, admin/user RBAC, admin panel  
> **Implementation roadmap:** [`docs/implementation-roadmap.md`](implementation-roadmap.md)

---

## 1. Overview

Zora is a self-hosted YouTube Music downloader and player. This spec adds:

- **Authentication** — local email/password signup & login, plus Google OAuth 2.0.
- **Two roles** — `admin` and `user` with strict server-side enforcement.
- **Admin panel** — user management, audit logs, server settings.
- **Playlist ownership** — each user owns their own playlists.

---

## 2. Roles & Permissions

### 2.1 Admin

| Capability | Details |
|---|---|
| Download songs & playlists | Trigger downloads, manage download queue |
| Server settings | Change download directory, default format/quality, duplicate settings |
| Library management | Delete songs from server, clear history |
| Admin panel | View all users (name, email, role, status, last login), activate/deactivate users, change roles |
| Playlists | Create, edit, delete own playlists |
| Playback | Stream any song from the shared library |
| Audit logs | View admin action history |

### 2.2 User

| Capability | Details |
|---|---|
| Playback | Stream any song from the shared library |
| Player controls | Play, pause, skip, seek, volume, shuffle, repeat |
| Personal playlists | Create, rename, delete, add/remove songs — own playlists only |
| Profile | View/update own name and password |

### 2.3 User Restrictions (Explicitly Denied)

- ❌ Cannot download songs or trigger any download
- ❌ Cannot access or change server settings (download path, format, quality)
- ❌ Cannot delete songs from the server library
- ❌ Cannot clear download history
- ❌ Cannot access admin panel or view other users
- ❌ Cannot modify, view, or delete other users' playlists
- ❌ Cannot directly download audio files from server (no `/downloads/<file>` access)

---

## 3. Authentication Methods

### 3.1 Local Auth (Email + Password)

- **Signup:** name, email, password, confirm password.
- **Login:** email + password.
- **Password hashing:** bcrypt via `werkzeug.security` (already a Flask dependency) or `passlib[bcrypt]`.
- **Password rules:** minimum 8 characters. No complexity requirement in v1.

### 3.2 Google OAuth 2.0

- **Library:** `Authlib` (recommended) or `Flask-Dance`.
- **Flow:** Authorization Code flow with PKCE.
- **Required scopes:** `openid`, `email`, `profile`.
- **Google Cloud Console setup required:**
  - Create OAuth 2.0 client credentials
  - Set authorized redirect URI: `{ZORA_BASE_URL}/api/auth/google/callback`
- **Env vars:**
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`

### 3.3 Account Linking Policy

| Scenario | Behavior |
|---|---|
| Google login, no existing account | Create new `user` account, `auth_provider = google`, `email_verified = true` |
| Google login, existing local account with same email | Link Google to existing account, set `auth_provider = hybrid`, set `google_sub` |
| Local signup, existing Google account with same email | Reject with "email already registered — try Google login" |
| Google login, existing account is deactivated | Reject login with "account disabled" |

### 3.4 Session Management

- **Strategy:** Server-side sessions with secure cookies (Flask-Login).
- **No JWT.** Simpler, safer for Flask SSR + JS app.
- **Cookie policy:**
  - `SESSION_COOKIE_HTTPONLY = True`
  - `SESSION_COOKIE_SECURE = True` (in production / HTTPS)
  - `SESSION_COOKIE_SAMESITE = "Lax"`
- **Session rotation:** regenerate session ID on login.
- **Session invalidation:** on logout, on password change.
- **Session lifetime:** 7 days default, configurable via `SESSION_LIFETIME_DAYS` env var.

---

## 4. First Admin Bootstrap

The first admin account is auto-created on server startup if no users exist.

**Required env vars:**

```env
ZORA_ADMIN_EMAIL=admin@example.com
ZORA_ADMIN_PASSWORD=strongpassword
ZORA_ADMIN_NAME=Admin
```

**Behavior:**
- On startup, if `users` table is empty AND env vars are set → create admin account.
- If `users` table is empty AND env vars are NOT set → log warning, app still starts but all protected routes return 403 until an admin is bootstrapped.
- The bootstrap admin has `role = admin`, `auth_provider = local`, `email_verified = true`.

---

## 5. Data Model Changes

### 5.1 New Table: `users`

```
id              INTEGER  PK, auto-increment
name            VARCHAR(100)  NOT NULL
email           VARCHAR(255)  NOT NULL, UNIQUE, INDEXED
password_hash   VARCHAR(255)  NULLABLE  (null for Google-only accounts)
role            VARCHAR(10)   NOT NULL, DEFAULT 'user'  CHECK(role IN ('admin', 'user'))
auth_provider   VARCHAR(10)   NOT NULL, DEFAULT 'local' CHECK(auth_provider IN ('local', 'google', 'hybrid'))
google_sub      VARCHAR(255)  NULLABLE, UNIQUE
avatar_url      VARCHAR(500)  NULLABLE
is_active       BOOLEAN       NOT NULL, DEFAULT TRUE
email_verified  BOOLEAN       NOT NULL, DEFAULT FALSE
created_at      DATETIME      NOT NULL, DEFAULT NOW
updated_at      DATETIME      NOT NULL, DEFAULT NOW
last_login_at   DATETIME      NULLABLE
```

### 5.2 New Table: `audit_logs`

```
id              INTEGER  PK, auto-increment
actor_user_id   INTEGER  FK -> users.id, INDEXED
action          VARCHAR(50)   NOT NULL  (e.g. DOWNLOAD_CREATE, SETTINGS_UPDATE, USER_ROLE_CHANGE, USER_DEACTIVATE, HISTORY_CLEAR, SONG_DELETE)
target_type     VARCHAR(30)   NULLABLE  (e.g. download, settings, user, playlist)
target_id       VARCHAR(50)   NULLABLE
metadata_json   TEXT          NULLABLE  (JSON blob with details)
ip_address      VARCHAR(45)   NULLABLE
user_agent      VARCHAR(500)  NULLABLE
created_at      DATETIME      NOT NULL, DEFAULT NOW
```

### 5.3 Modified Table: `playlists`

**Add column:**

```
owner_user_id   INTEGER  FK -> users.id, INDEXED, NOT NULL (after migration)
```

**Changed constraint:**
- Remove global unique constraint on `name`.
- Add unique constraint on `(owner_user_id, LOWER(name))` — enforced at application level via query.

### 5.4 Optional (Deferred): `password_reset_tokens`

```
id              INTEGER  PK
user_id         INTEGER  FK -> users.id
token_hash      VARCHAR(255)  NOT NULL, UNIQUE
expires_at      DATETIME      NOT NULL
used            BOOLEAN       DEFAULT FALSE
created_at      DATETIME      DEFAULT NOW
```

---

## 6. API Routes

### 6.1 New Auth Routes

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/api/auth/signup` | Public | Create new user account |
| POST | `/api/auth/login` | Public | Login with email/password |
| POST | `/api/auth/logout` | Authenticated | Destroy session |
| GET | `/api/auth/me` | Authenticated | Get current user profile |
| POST | `/api/auth/password/change` | Authenticated | Change own password |
| POST | `/api/auth/password/reset/request` | Public | Request password reset email (Phase 4) |
| POST | `/api/auth/password/reset/confirm` | Public | Confirm password reset with token (Phase 4) |
| GET | `/api/auth/google/start` | Public | Redirect to Google OAuth consent |
| GET | `/api/auth/google/callback` | Public | Handle Google OAuth callback |

### 6.2 New Admin Routes

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/api/admin/users` | Admin | List all users (paginated, searchable) |
| GET | `/api/admin/users/<id>` | Admin | Get single user details |
| PATCH | `/api/admin/users/<id>` | Admin | Update user role, activate/deactivate |
| GET | `/api/admin/audit-logs` | Admin | View audit log (paginated, filterable) |

### 6.3 Existing Route Authorization Updates

| Endpoint | Current Access | New Access |
|---|---|---|
| `GET /` | Public | Public (redirects to login if not authenticated) |
| `POST /api/download` | Public | **Admin only** |
| `POST /api/playlist-download/start` | Public | **Admin only** |
| `POST /api/queue/add` | Public | **Admin only** |
| `POST /api/queue/remove/<id>` | Public | **Admin only** |
| `POST /api/queue/clear` | Public | **Admin only** |
| `GET /api/settings` | Public | **Admin only** |
| `POST /api/settings` | Public | **Admin only** |
| `POST /api/history/clear` | Public | **Admin only** |
| `POST /api/history/delete/<id>` | Public | **Admin only** |
| `GET /downloads/<filename>` | Public | **Admin only** |
| `POST /api/info` | Public | **Admin only** |
| `POST /api/search` | Public | **Admin only** |
| `GET /api/history` | Public | **Authenticated** (read-only library) |
| `GET /play/<filename>` | Public | **Authenticated** (streaming) |
| `GET /api/playlists` | Public | **Authenticated** (own playlists only) |
| `POST /api/playlists` | Public | **Authenticated** (creates under own user) |
| `DELETE /api/playlists/<id>` | Public | **Authenticated** (own playlists only) |
| `GET /api/playlists/<id>/songs` | Public | **Authenticated** (own playlists only) |
| `POST /api/playlists/<id>/songs` | Public | **Authenticated** (own playlists only) |
| `DELETE /api/playlists/<id>/songs/<sid>` | Public | **Authenticated** (own playlists only) |

---

## 7. Architectural Changes Required

These changes are prerequisites — do them before or during Phase 1.

| # | Change | Why | Effort |
|---|---|---|---|
| 7.1 | Delete `server.py` | Dead code, duplicate app with no auth — security hole | 1 min |
| 7.2 | Split `routes/api.py` into focused files | 800-line god file, too large for safe decorator application | ~30 min |
| 7.3 | Add `app/auth/` package | No auth layer exists at all | Core Phase 1 work |
| 7.4 | Default-deny `before_request` middleware | Prevents missed route guards forever | ~15 min |
| 7.5 | Update `api.js` with CSRF + 401/403 handling | Frontend can't talk to authenticated backend otherwise | ~30 min |
| 7.6 | Login/signup as SPA views | Matches existing single-page architecture pattern | Phase 1 frontend work |

### 7.1 Delete `server.py`

`server.py` is a legacy duplicate of the entire app (own routes, JSON history, own settings). It has no auth and will never get guards. **Delete it.** The real app runs through `run.py` → `app/__init__.py`.

### 7.2 Split `routes/api.py` (~800 lines)

Currently a god file mixing downloads, search, streaming, playlist-downloads, and queue. Split into focused modules so auth decorators are applied cleanly:

```
routes/
├── api.py              → keeps only GET / (index route)
├── download.py         → /api/download, /api/playlist-download/* (admin-only)
├── search.py           → /api/search, /api/info (admin-only)
├── stream.py           → /play/<filename>, /api/thumbnails/* (authenticated)
├── history.py          → unchanged (admin for delete/clear, authenticated for read)
├── playlists.py        → unchanged (authenticated, ownership-scoped)
├── settings.py         → unchanged (admin-only)
├── queue.py            → unchanged (admin-only)
```

### 7.3 Add `app/auth/` package

New package for all authentication logic:

```
app/auth/
├── __init__.py         → init_auth(app) — Flask-Login setup, user_loader
├── decorators.py       → @admin_required, @owns_playlist
├── routes.py           → /api/auth/* (login, signup, logout, me, password)
├── google.py           → /api/auth/google/* (OAuth helpers, Phase 2)
```

### 7.4 Add default-deny middleware in `app/__init__.py`

Add `@app.before_request` that requires authentication on ALL routes by default, with an explicit allowlist:

```python
PUBLIC_ENDPOINTS = {
    'api.index',              # GET /
    'auth.login',             # POST /api/auth/login
    'auth.signup',            # POST /api/auth/signup
    'auth.google_start',      # GET /api/auth/google/start
    'auth.google_callback',   # GET /api/auth/google/callback
    'static',                 # static files
}
```

Any new route is **denied by default** unless explicitly allowlisted. This eliminates Risk 3 (missing a guard).

### 7.5 Add auth/CSRF support to frontend `api.js`

Update the `API` object to:
1. Include CSRF token in `X-CSRFToken` header on every POST/PATCH/DELETE.
2. Global 401 handler → redirect to login page.
3. Global 403 handler → show "not authorized" toast.

### 7.6 Add login/signup as SPA views (not separate HTML)

Current app is a single-page app inside `index.html`. Keep that pattern — add login/signup as JS-rendered views (like the existing download/library/playlists views) rather than separate HTML templates. The `@app.before_request` + `GET /api/auth/me` check controls which view renders.

---

## 8. Backend Implementation

### 8.1 New Dependencies

Add to `requirements.txt`:

```
Flask-Login>=0.6.0
authlib>=1.3.0
passlib[bcrypt]>=1.7.0
Flask-Limiter>=3.0.0
Flask-WTF>=1.2.0
```

### 8.2 Decorators

```python
# app/auth/decorators.py

@login_required          # Flask-Login built-in — 401 if not authenticated
@admin_required          # Custom — 403 if role != 'admin'
@owns_playlist(param)    # Custom — 403 if playlist.owner_user_id != current_user.id (admin bypasses)
```

### 8.3 New File Structure

```
app/
├── auth/
│   ├── __init__.py
│   ├── decorators.py        # @admin_required, @owns_playlist
│   ├── routes.py             # /api/auth/* endpoints
│   └── google.py             # Google OAuth helpers
├── admin/
│   ├── __init__.py
│   └── routes.py             # /api/admin/* endpoints
├── models/
│   ├── user.py               # User model
│   └── audit_log.py          # AuditLog model
```

### 8.4 Rate Limiting

```python
# Applied via Flask-Limiter

POST /api/auth/login          → 5 per minute per IP
POST /api/auth/signup         → 3 per minute per IP
POST /api/auth/password/reset → 3 per minute per IP
```

### 8.5 CSRF Protection

- Use `Flask-WTF` CSRFProtect for all state-changing endpoints.
- Frontend sends CSRF token in `X-CSRFToken` header (fetched from cookie or meta tag).
- Exempt Google OAuth callback from CSRF (uses `state` param instead).

---

## 8. Frontend Changes

### 8.1 New Pages/Screens

| Screen | Description |
|---|---|
| **Login** | Email/password form + "Continue with Google" button + link to signup |
| **Signup** | Name, email, password, confirm password + "Continue with Google" + link to login |
| **Admin Panel** | User table with search/filter/pagination, role dropdown, activate/deactivate toggle |
| **Profile** | View/edit name, change password |

### 8.2 Role-Aware UI Changes

| Element | Admin | User |
|---|---|---|
| Search bar + download button | ✅ Visible | ❌ Hidden |
| Download queue panel | ✅ Visible | ❌ Hidden |
| Settings page/button | ✅ Visible | ❌ Hidden |
| Delete song from library | ✅ Visible | ❌ Hidden |
| Clear history button | ✅ Visible | ❌ Hidden |
| Admin panel nav link | ✅ Visible | ❌ Hidden |
| Library (browse/stream) | ✅ Visible | ✅ Visible |
| Player controls | ✅ Visible | ✅ Visible |
| Personal playlists | ✅ Visible | ✅ Visible |
| User avatar/logout | ✅ Visible | ✅ Visible |

### 8.3 Auth Flow in Frontend

1. On page load → `GET /api/auth/me`
   - If 401 → redirect to login page
   - If 200 → store user in JS state, render role-appropriate UI
2. Login/signup success → redirect to home (`/`)
3. Logout → `POST /api/auth/logout` → redirect to login

---

## 9. Database Setup (Fresh Start)

> **Note:** All current data (songs, playlists, history) is test data. No migration needed — we delete the old database and start clean with the new schema.

### Step 1: Delete old database

Delete `data.db` and `zora.db`. The new schema includes `users`, `audit_logs`, and the updated `playlists` table with `owner_user_id` from the start.

### Step 2: `db.create_all()`

On startup, `create_all()` builds all tables fresh (including `users`, `audit_logs`, updated `playlists`). No Alembic/Flask-Migrate needed.

### Step 3: Bootstrap admin

On startup, if `users` table is empty and `ZORA_ADMIN_*` env vars are set, insert admin row.

### Step 4: Deploy guards

Add `@login_required` and `@admin_required` to all protected routes.

### Step 5: Frontend release

Deploy auth screens and role-aware UI controls.

### Step 6: Smoke test

Run permission matrix tests before enabling public access.

---

## 10. Security Checklist

- [ ] Passwords hashed with bcrypt (never stored plain text)
- [ ] Rate limiting on login, signup, password reset
- [ ] CSRF tokens on all POST/PATCH/DELETE endpoints
- [ ] Email input validated and normalized (lowercase, trimmed)
- [ ] Server-side role checks on every protected route (never rely on UI hiding alone)
- [ ] Session cookie: HttpOnly, Secure (HTTPS), SameSite=Lax
- [ ] Session ID rotated on login
- [ ] Session invalidated on logout and password change
- [ ] Google OAuth `state` parameter validated to prevent CSRF
- [ ] Google client secret stored in env var, never committed to git
- [ ] `SECRET_KEY` is strong and not default
- [ ] Security headers added: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`
- [ ] Auth failures logged (failed logins, blocked IPs)
- [ ] Admin actions recorded in `audit_logs`
- [ ] No secrets in client-side code or API responses

---

## 11. Environment Variables (Complete)

```env
# Server
ZORA_HOST=0.0.0.0
ZORA_PORT=5001
SECRET_KEY=<strong-random-key>

# Storage
ZORA_DOWNLOAD_DIR=/absolute/path/to/music

# Admin bootstrap
ZORA_ADMIN_EMAIL=admin@example.com
ZORA_ADMIN_PASSWORD=<strong-password>
ZORA_ADMIN_NAME=Admin

# Google OAuth (Phase 2)
GOOGLE_CLIENT_ID=<from-google-console>
GOOGLE_CLIENT_SECRET=<from-google-console>

# Session
SESSION_LIFETIME_DAYS=7
```

---

## 12. Test Plan

### 12.1 Unit Tests

- Password hash and verify
- `@admin_required` decorator denies user role
- `@owns_playlist` decorator denies wrong owner, allows admin override
- Email normalization and validation
- Session rotation on login

### 12.2 Integration Tests

- Signup → login → access protected route → logout
- Google OAuth callback → account creation/linking
- Admin endpoint returns 403 for `user` role
- User can only see/modify own playlists
- Deactivated user cannot login
- Rate limiter triggers after threshold

### 12.3 E2E Tests (Playwright)

- User cannot see download/settings/admin UI elements
- Admin can download, manage settings, view users
- Playback works for both roles
- Google login flow (with mock or test account)

---

## 13. Release Phases

### Phase 1 — Local Auth + RBAC + Playlist Ownership
- User model, signup, login, logout
- `@login_required`, `@admin_required` decorators
- Playlist `owner_user_id` migration
- Role-aware frontend (hide admin controls for users)
- Admin bootstrap from env vars

### Phase 2 — Google OAuth
- Authlib integration
- Google login/signup flow
- Account linking (Google ↔ local)
- "Continue with Google" UI

### Phase 3 — Admin Panel + Audit Logs
- `/api/admin/users` CRUD
- Admin panel frontend (user table, search, role management)
- Audit log recording and viewing

### Phase 4 — Password Reset + Security Hardening
- Email-based password reset flow (requires SMTP config)
- Email verification for local signups
- Security headers middleware
- Comprehensive rate limiting tuning

---

## 14. Risks & Mitigations

### ~~Risk 1: Database Migration Data Loss~~ — ELIMINATED

All current data is test data. We delete the old DB and start fresh with `db.create_all()`. No migration tooling needed. See §9.

### ~~Risk 2: Playlist Ownership Split~~ — ELIMINATED

No existing playlists to migrate. New `playlists` table includes `owner_user_id` from day one. Playlist queries filter by `owner_user_id = current_user.id`. Unique constraint is per-owner at application level.

### Risk 3: Missing a Route Guard (Security Hole)

**Problem:** 22+ existing endpoints are currently public. Missing `@login_required` or `@admin_required` on even one is a security hole.

**Mitigation:**
1. **Default-deny middleware** — add a `@app.before_request` hook that requires authentication on ALL `/api/*` routes by default, with an explicit allowlist for public endpoints (`/api/auth/login`, `/api/auth/signup`, `/api/auth/google/*`).
2. **Route audit script** — create `scripts/audit_routes.py` that lists every registered route and its decorators. Run in CI to catch unprotected endpoints.
3. **Role-matrix integration tests** — for every endpoint, test three actors: guest (expect 401), user (expect 403 on admin routes), admin (expect 200). See §14 Risk 8 for the test grid.

### Risk 4: Google Auth Account Linking Edge Cases

**Problem:** "Same email, different auth provider" scenarios can create duplicate users or lock people out.

**Mitigation:**
1. **Single user row per email** — enforced by `UNIQUE(email)` constraint.
2. **Linking table in §3.3** — defines exact behavior for all four scenarios.
3. **Additional edge cases to handle:**
   - User signs up locally → later clicks "Continue with Google" with same email → merge: set `auth_provider = hybrid`, store `google_sub`, keep existing password hash.
   - User signs up via Google → later tries local signup with same email → reject with clear message: "Account exists. Use Google login or reset password."
   - Google returns an unverified email → reject login; require verified Google email.
4. **Test:** Integration test for each linking scenario in §3.3 table.

### Risk 5: Session Security & CSRF Bypass

**Problem:** Misconfigured cookies or missing CSRF allows session hijacking or cross-site attacks.

**Mitigation:**
1. **Cookie settings hardcoded in app factory** — not configurable by users to avoid accidental weakening (§3.4).
2. **CSRF via Flask-WTF** — auto-applied to all POST/PATCH/DELETE. Frontend reads token from `<meta>` tag or cookie and sends in `X-CSRFToken` header.
3. **Exempt list** — only Google OAuth callback exempt from CSRF (it uses `state` param).
4. **Test:** Integration test that sends POST without CSRF token → expect 400.

### Risk 6: Admin Bootstrap & Recovery

**Problem:** How is the first admin created? What if admin forgets password and Google isn't configured?

**Mitigation:**
1. **Bootstrap from env vars** (§4) — `ZORA_ADMIN_EMAIL`, `ZORA_ADMIN_PASSWORD`, `ZORA_ADMIN_NAME`.
2. **CLI recovery command** — add `python manage.py reset-admin` that:
   - Reads `ZORA_ADMIN_EMAIL` and `ZORA_ADMIN_PASSWORD` from env.
   - If user exists, resets password hash and sets `is_active = True`.
   - If user doesn't exist, creates admin account.
   - Runs without the web server (direct DB access).
3. **Prevent last-admin demotion** — API refuses to change role of the last remaining active admin to `user`, and refuses to deactivate them. Returns 409.
4. **Log bootstrap events** — print to console on startup: "Admin account created for admin@example.com" or "Admin account already exists, skipping bootstrap."

### Risk 7: Global Queue/Library Behavior With Roles

**Problem:** Download queue and library are global server resources. With roles, need clear rules for visibility and control.

**Mitigation:**
1. **Library is shared read-only** — all authenticated users (admin + user) can browse and stream the same library. Library content is server-level, not per-user.
2. **Queue is admin-only** — users never see the download queue, cannot add to it, and are unaffected by queue state.
3. **Active download visibility** — users do NOT see download progress banners or notifications. The UI simply doesn't render queue/download components for `user` role (§8.2).
4. **Downloads auto-appear in library** — when admin downloads a song, it appears in the shared library automatically. Users see it on next library refresh. No special sync needed.
5. **No per-user download quotas in v1** — since only admin downloads, no quota system needed.

### Risk 8: Test Coverage Explosion

**Problem:** Every endpoint now needs testing for 3 actors (guest, user, admin). With 22+ endpoints, that's 66+ test cases minimum.

**Mitigation:**
1. **Role-matrix test helper** — create a pytest fixture/helper that takes `(endpoint, method, actor, expected_status)` and auto-generates test cases:

```python
# tests/test_role_matrix.py
ROLE_MATRIX = [
    # (method, endpoint, guest, user, admin)
    ("POST", "/api/download",            401, 403, 200),
    ("POST", "/api/settings",            401, 403, 200),
    ("GET",  "/api/history",             401, 200, 200),
    ("GET",  "/play/test.m4a",           401, 200, 200),
    ("POST", "/api/playlists",           401, 201, 201),
    ("POST", "/api/history/clear",       401, 403, 200),
    ("POST", "/api/history/delete/1",    401, 403, 200),
    ("POST", "/api/queue/add",           401, 403, 200),
    ("POST", "/api/queue/clear",         401, 403, 200),
    ("GET",  "/api/settings",            401, 403, 200),
    ("GET",  "/api/admin/users",         401, 403, 200),
    # ... all endpoints
]
```

2. **Run in CI** — matrix tests run on every PR.
3. **Playwright E2E** — verify UI hides admin elements for user role, shows them for admin.

### ~~Risk 9: Migration Rollback & Restart Safety~~ — ELIMINATED

No migration needed. Fresh `db.create_all()` on clean database. If anything goes wrong, just delete `data.db` and restart.

---

## 15. Acceptance Criteria

1. ✅ Unauthenticated users see only login/signup page
2. ✅ Admin can perform all server-changing operations (download, settings, delete, clear)
3. ✅ User receives 403 on any admin-only API endpoint
4. ✅ User can stream songs and manage only their own playlists
5. ✅ Google login creates/links accounts correctly
6. ✅ Admin panel shows all users with name, email, role, status, created date, last login
7. ✅ All POST/PATCH/DELETE routes enforce auth + role checks server-side
8. ✅ First admin is bootstrapped from env vars on empty database
9. ✅ Existing playlists are migrated to admin ownership
10. ✅ Audit log records admin actions with actor, action, target, timestamp, IP
