/**
 * Zora Service Worker
 * Strategy:
 *   - App shell (HTML, CSS, JS, fonts):  Cache-First with network fallback
 *   - API calls:                         Network-First with cache fallback
 *   - Audio streams (/play/…):           LRU cache (instant replay for recently played tracks)
 *   - Thumbnails (/api/thumbnails/…):    Stale-While-Revalidate
 */

const CACHE_VERSION = 'v5';
const SHELL_CACHE = `zora-shell-${CACHE_VERSION}`;
const THUMB_CACHE = `zora-thumbs-${CACHE_VERSION}`;
const API_CACHE = `zora-api-${CACHE_VERSION}`;
// Audio cache is version-independent — survives SW updates, cleared on logout
const AUDIO_CACHE = 'zora-audio-lru';
const AUDIO_MAX_ENTRIES = 40;

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
    const CURRENT = new Set([SHELL_CACHE, THUMB_CACHE, API_CACHE, AUDIO_CACHE]);

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

    // 1. Audio streams — LRU cache for instant replay
    if (url.pathname.startsWith('/play/')) {
        if (request.method === 'GET') {
            event.respondWith(handleAudioFetch(request));
        }
        return;
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

// ─── Audio LRU Cache ────────────────────────────────────────────────────────

/**
 * Handle /play/ requests with an LRU audio cache.
 * - Cache hit: serve instantly (slicing for Range requests)
 * - Cache miss: fetch from network; cache full 200 responses for future replay
 * - Cache write errors never break online playback
 */
async function handleAudioFetch(request) {
    const cache = await caches.open(AUDIO_CACHE);
    const cacheKey = new Request(new URL(request.url).pathname);
    const rangeHeader = request.headers.get('Range');

    // 1. Try cache — instant replay
    const cached = await cache.match(cacheKey);
    if (cached) {
        if (rangeHeader) {
            try {
                return await serveRangeFromCache(cached, rangeHeader);
            } catch {
                // Corrupted entry — evict and fall through to network
                await cache.delete(cacheKey);
            }
        } else {
            // LRU touch: re-insert to move to end of insertion order
            cache.delete(cacheKey).then(() => cache.put(cacheKey, cached.clone())).catch(() => {});
            return cached;
        }
    }

    // 2. Network fetch — cache errors must never block playback
    let response;
    try {
        response = await fetch(request);
    } catch {
        return new Response('Audio unavailable offline', {
            status: 503,
            headers: { 'Content-Type': 'text/plain' },
        });
    }

    // 3. Cache full 200 responses in the background (preload fetches)
    if (response.status === 200) {
        try {
            await cache.put(cacheKey, response.clone());
            await trimAudioCache(cache);
        } catch { /* QuotaExceeded or write error — swallow, playback continues */ }
    }

    return response;
}

/**
 * Slice a cached full response to serve an HTTP 206 Range response.
 * Supports standard ranges (bytes=N-M, bytes=N-) and suffix ranges (bytes=-N).
 */
async function serveRangeFromCache(cachedResponse, rangeHeader) {
    const body = await cachedResponse.clone().arrayBuffer();
    const size = body.byteLength;

    const match = rangeHeader.match(/^bytes=(\d*)-(\d*)$/);
    if (!match) {
        // Unknown range format (multi-range, etc.) — return full response
        return new Response(body, { status: 200, headers: cachedResponse.headers });
    }

    const startStr = match[1];
    const endStr = match[2];
    let start, end;

    if (startStr === '' && endStr !== '') {
        // Suffix range: bytes=-N (last N bytes)
        const suffix = Number(endStr);
        if (!Number.isFinite(suffix) || suffix <= 0) {
            return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
        }
        start = Math.max(0, size - suffix);
        end = size - 1;
    } else if (startStr !== '') {
        start = Number(startStr);
        end = endStr ? Math.min(Number(endStr), size - 1) : size - 1;
        if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start) {
            return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
        }
    } else {
        // Both empty — invalid
        return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
    }

    if (start >= size) {
        return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
    }

    const slice = body.slice(start, end + 1);
    const headers = new Headers({
        'Content-Type': cachedResponse.headers.get('Content-Type') || 'audio/mpeg',
        'Content-Length': String(slice.byteLength),
        'Content-Range': `bytes ${start}-${end}/${size}`,
        'Accept-Ranges': 'bytes',
    });
    // Forward cache-related headers from the original server response
    for (const h of ['ETag', 'Last-Modified', 'Cache-Control']) {
        const v = cachedResponse.headers.get(h);
        if (v) headers.set(h, v);
    }
    return new Response(slice, { status: 206, headers });
}

/** Evict oldest entries when audio cache exceeds the max. */
async function trimAudioCache(cache) {
    const keys = await cache.keys();
    if (keys.length <= AUDIO_MAX_ENTRIES) return;

    const toDelete = keys.length - AUDIO_MAX_ENTRIES;
    for (let i = 0; i < toDelete; i++) {
        await cache.delete(keys[i]);
    }
}

// ─── Message handler (logout cache clearing) ────────────────────────────────

self.addEventListener('message', event => {
    if (event.data && event.data.type === 'CLEAR_AUDIO_CACHE') {
        event.waitUntil(caches.delete(AUDIO_CACHE));
    }
});

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
