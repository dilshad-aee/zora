/**
 * Zora Service Worker
 * Strategy:
 *   - App shell (HTML, CSS, JS, fonts):  Cache-First with network fallback
 *   - API calls:                         Network-First with cache fallback
 *   - Audio streams (/play/…):           Network-only (too large to cache)
 *   - Thumbnails (/api/thumbnails/…):    Stale-While-Revalidate
 */

const CACHE_VERSION = 'v4';
const SHELL_CACHE = `zora-shell-${CACHE_VERSION}`;
const THUMB_CACHE = `zora-thumbs-${CACHE_VERSION}`;
const API_CACHE = `zora-api-${CACHE_VERSION}`;

// Core app shell assets cached on install
const SHELL_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/js/api.js',
    '/static/js/ui.js',
    '/static/js/player.js',
    '/static/js/library.js',
    '/static/js/playlists.js',
    '/static/js/downloads.js',
    '/static/js/admin.js',
    '/static/js/playback.js',
    '/static/logo.png',
    '/static/images/icons/icon-192x192.png',
    '/static/images/icons/icon-512x512.png',
    '/static/manifest.json',
    // Google Fonts cached via CDN (fetched at install)
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap',
];

// ─── Install: pre-cache the shell ───────────────────────────────────────────

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(SHELL_CACHE)
            .then(cache => cache.addAll(SHELL_ASSETS))
            .then(() => self.skipWaiting())
    );
});

// ─── Activate: clean up old caches ──────────────────────────────────────────

self.addEventListener('activate', event => {
    const CURRENT = new Set([SHELL_CACHE, THUMB_CACHE, API_CACHE]);

    event.waitUntil(
        caches.keys()
            .then(keys => Promise.all(
                keys.filter(k => !CURRENT.has(k)).map(k => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

// ─── Fetch: routing logic ────────────────────────────────────────────────────

self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // 1. Audio streams — always network-only (range requests, too large)
    if (url.pathname.startsWith('/play/')) {
        return; // let browser handle normally
    }

    // 2. Thumbnails — Stale-While-Revalidate
    if (url.pathname.startsWith('/api/thumbnails/')) {
        event.respondWith(staleWhileRevalidate(request, THUMB_CACHE));
        return;
    }

    // 3. API calls
    if (url.pathname.startsWith('/api/')) {
        // Auth endpoints — always network-only, never cache
        if (url.pathname.startsWith('/api/auth/')) {
            event.respondWith(fetch(request));
            return;
        }

        // Never cache non-GET API calls and never apply short timeout to them.
        // Large playlist extraction uses POST and can legitimately take > 4s.
        if (request.method !== 'GET') {
            event.respondWith(fetch(request));
            return;
        }

        // Use endpoint-aware timeouts for heavy GET endpoints.
        let timeoutMs = 10000;
        if (url.pathname.startsWith('/api/history')) {
            timeoutMs = 20000;
        } else if (
            url.pathname.startsWith('/api/playlist-download/status/') ||
            url.pathname.startsWith('/api/status/')
        ) {
            timeoutMs = 12000;
        }

        event.respondWith(networkFirst(request, API_CACHE, timeoutMs));
        return;
    }

    // 4. App shell & static assets — Cache-First
    event.respondWith(cacheFirst(request, SHELL_CACHE));
});

// ─── Strategies ─────────────────────────────────────────────────────────────

/** Cache-First: serve from cache, fall back to network then update cache */
async function cacheFirst(request, cacheName) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request);
    if (cached) return cached;

    try {
        const response = await fetch(request);
        if (response.ok) cache.put(request, response.clone());
        return response;
    } catch {
        // Offline fallback for navigation requests
        if (request.mode === 'navigate') {
            const shell = await cache.match('/');
            if (shell) return shell;
        }
        return new Response('Offline — please reconnect to use Zora.', {
            status: 503,
            headers: { 'Content-Type': 'text/plain' },
        });
    }
}

/** Network-First: try network, fall back to cache; timeout after ms */
async function networkFirst(request, cacheName, timeoutMs = 4000) {
    const cache = await caches.open(cacheName);

    const networkPromise = fetch(request).then(response => {
        if (response.ok) cache.put(request, response.clone());
        return response;
    });

    const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), timeoutMs)
    );

    try {
        return await Promise.race([networkPromise, timeoutPromise]);
    } catch {
        const cached = await cache.match(request);
        if (cached) return cached;
        return new Response(JSON.stringify({ error: 'Offline' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' },
        });
    }
}

/** Stale-While-Revalidate: serve cached immediately, update in background */
async function staleWhileRevalidate(request, cacheName) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request);

    // Kick off a background update regardless
    const fetchPromise = fetch(request).then(response => {
        if (response.ok) cache.put(request, response.clone());
        return response;
    }).catch(() => null);

    return cached || fetchPromise;
}

// ─── Background Sync (future-proof hook) ─────────────────────────────────────

self.addEventListener('sync', event => {
    if (event.tag === 'sync-downloads') {
        // Placeholder for future background download sync
        event.waitUntil(Promise.resolve());
    }
});

// ─── Push Notifications (future-proof hook) ─────────────────────────────────

self.addEventListener('push', event => {
    if (!event.data) return;
    const data = event.data.json();
    event.waitUntil(
        self.registration.showNotification(data.title || 'Zora', {
            body: data.body || '',
            icon: '/static/images/icons/icon-192x192.png',
            badge: '/static/images/icons/icon-72x72.png',
        })
    );
});
