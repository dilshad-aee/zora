/**
 * Zora - Synced Lyrics Module
 * Fetches and displays synced lyrics from LRCLIB.net
 * Apple Music / Spotify style full-screen lyrics panel
 *
 * Dependencies: player.js, ui.js
 */

const Lyrics = {
    _cache: new Map(),
    _panel: null,
    _container: null,
    _lines: [],
    _activeLine: -1,
    _isOpen: false,
    _isSynced: false,
    _currentKey: null,
    _scrollTimeout: null,
    _userScrolling: false,

    /**
     * Initialize lyrics module — create panel, hook into player
     */
    init() {
        this._createPanel();

        if (Player.audio) {
            Player.audio.addEventListener('timeupdate', () => {
                if (this._isOpen && this._isSynced) {
                    this._syncToTime(Player.audio.currentTime);
                }
            });

            // Re-fetch lyrics when a new track loads while the panel is open
            Player.audio.addEventListener('loadedmetadata', () => {
                if (this._isOpen && Player.currentTrack) {
                    const key = `${Player.currentTrack.title || ''}|${Player.currentTrack.artist || ''}`;
                    if (this._currentKey !== key) {
                        // Update header info
                        const titleEl = document.getElementById('lyricsPanelTitle');
                        const artistEl = document.getElementById('lyricsPanelArtist');
                        if (titleEl) titleEl.textContent = Player.currentTrack.title || 'Unknown Title';
                        if (artistEl) artistEl.textContent = Player.currentTrack.artist || 'Unknown Artist';
                        const backdrop = this._panel?.querySelector('.lyrics-panel__backdrop');
                        if (backdrop && Player.currentTrack.thumbnail) {
                            backdrop.style.backgroundImage = `url('${Player.currentTrack.thumbnail}')`;
                        }
                        this._onTrackChange();
                    }
                }
            });
        }
    },

    /**
     * Create the lyrics panel DOM and append to body
     */
    _createPanel() {
        if (this._panel) return;

        const panel = document.createElement('div');
        panel.id = 'lyricsPanel';
        panel.className = 'lyrics-panel';
        panel.innerHTML = `
            <div class="lyrics-panel__backdrop"></div>
            <div class="lyrics-panel__header">
                <button class="lyrics-panel__close" onclick="Lyrics.close()">
                    <i class="fas fa-chevron-down"></i>
                </button>
                <div class="lyrics-panel__track-info">
                    <div class="lyrics-panel__title" id="lyricsPanelTitle">—</div>
                    <div class="lyrics-panel__artist" id="lyricsPanelArtist">—</div>
                </div>
            </div>
            <div class="lyrics-panel__body">
                <div class="lyrics-panel__scroll" id="lyricsScroll">
                    <div class="lyrics-panel__content" id="lyricsContent"></div>
                </div>
            </div>
        `;

        document.body.appendChild(panel);
        this._panel = panel;
        this._container = document.getElementById('lyricsContent');

        // Track user scrolling to pause auto-scroll briefly
        const scroll = document.getElementById('lyricsScroll');
        if (scroll) {
            let scrollTimer;
            scroll.addEventListener('touchstart', () => { this._userScrolling = true; }, { passive: true });
            scroll.addEventListener('touchend', () => {
                clearTimeout(scrollTimer);
                scrollTimer = setTimeout(() => { this._userScrolling = false; }, 3000);
            }, { passive: true });
            scroll.addEventListener('wheel', () => {
                this._userScrolling = true;
                clearTimeout(scrollTimer);
                scrollTimer = setTimeout(() => { this._userScrolling = false; }, 3000);
            }, { passive: true });
        }
    },

    /**
     * Open the lyrics panel
     */
    open() {
        if (!this._panel) this._createPanel();

        const track = Player.currentTrack;
        if (!track) {
            UI.toast('No track playing', 'error');
            return;
        }

        // Update track info
        const titleEl = document.getElementById('lyricsPanelTitle');
        const artistEl = document.getElementById('lyricsPanelArtist');
        if (titleEl) titleEl.textContent = track.title || 'Unknown Title';
        if (artistEl) artistEl.textContent = track.artist || 'Unknown Artist';

        // Set backdrop from thumbnail
        const backdrop = this._panel.querySelector('.lyrics-panel__backdrop');
        if (backdrop && track.thumbnail) {
            backdrop.style.backgroundImage = `url('${track.thumbnail}')`;
        }

        this._panel.classList.add('open');
        this._isOpen = true;
        document.body.style.overflow = 'hidden';

        // Fetch lyrics if needed
        const key = `${track.title || ''}|${track.artist || ''}`;
        if (this._currentKey !== key) {
            this._onTrackChange();
        } else if (this._isSynced) {
            this._syncToTime(Player.audio.currentTime);
        }
    },

    /**
     * Close the lyrics panel
     */
    close() {
        if (this._panel) {
            this._panel.classList.remove('open');
        }
        this._isOpen = false;
        document.body.style.overflow = '';
    },

    /**
     * Toggle the lyrics panel
     */
    toggle() {
        if (this._isOpen) {
            this.close();
        } else {
            this.open();
        }
    },

    /**
     * Handle track change — reset state and fetch new lyrics
     */
    _onTrackChange() {
        const track = Player.currentTrack;
        if (!track) return;

        const key = `${track.title || ''}|${track.artist || ''}`;
        this._currentKey = key;
        this._lines = [];
        this._activeLine = -1;
        this._isSynced = false;

        // Show loading state
        this._renderLoading();

        const duration = Player.audio && Number.isFinite(Player.audio.duration) ? Player.audio.duration : 0;
        this.fetchForTrack(track.title || '', track.artist || '', duration).then(result => {
            // Guard: track may have changed while fetching
            if (this._currentKey !== key) return;

            if (!result) {
                this._renderEmpty();
                return;
            }

            if (result.synced && result.lines.length) {
                this._lines = result.lines;
                this._isSynced = true;
                this._renderLyrics();
                if (this._isOpen) {
                    this._syncToTime(Player.audio.currentTime);
                }
            } else if (result.plain) {
                this._isSynced = false;
                this._renderPlain(result.plain);
            } else {
                this._renderEmpty();
            }
        }).catch(() => {
            if (this._currentKey !== key) return;
            this._renderEmpty();
        });
    },

    /**
     * Fetch lyrics from LRCLIB for a track
     */
    async fetchForTrack(title, artist, duration) {
        const key = `${title}|${artist}`;
        if (this._cache.has(key)) return this._cache.get(key);

        const cleanedTitle = this._cleanTitle(title);

        const params = new URLSearchParams();
        params.set('track_name', cleanedTitle);
        if (artist) params.set('artist_name', artist);

        try {
            const resp = await fetch(`https://lrclib.net/api/search?${params.toString()}`);
            if (!resp.ok) {
                this._cache.set(key, null);
                return null;
            }

            const results = await resp.json();
            if (!results || !results.length) {
                this._cache.set(key, null);
                return null;
            }

            // Pick best match: prefer synced lyrics, then closest duration
            const best = this._pickBestMatch(results, duration);
            if (!best) {
                this._cache.set(key, null);
                return null;
            }

            let result;
            if (best.syncedLyrics) {
                const lines = this._parseLRC(best.syncedLyrics);
                result = { synced: true, lines, plain: best.plainLyrics || null };
            } else if (best.plainLyrics) {
                result = { synced: false, lines: [], plain: best.plainLyrics };
            } else {
                result = null;
            }

            this._cache.set(key, result);
            return result;
        } catch {
            this._cache.set(key, null);
            return null;
        }
    },

    /**
     * Pick the best match from LRCLIB results
     */
    _pickBestMatch(results, duration) {
        // Separate into synced and unsynced
        const synced = results.filter(r => r.syncedLyrics);
        const pool = synced.length ? synced : results;

        if (!duration) return pool[0];

        // Sort by closest duration match
        pool.sort((a, b) => {
            const diffA = Math.abs((a.duration || 0) - duration);
            const diffB = Math.abs((b.duration || 0) - duration);
            return diffA - diffB;
        });

        return pool[0];
    },

    /**
     * Parse LRC format string into [{time, text}] array
     */
    _parseLRC(lrcString) {
        if (!lrcString) return [];

        const lines = [];
        const regex = /\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]\s*(.*)/;

        for (const raw of lrcString.split('\n')) {
            const match = raw.match(regex);
            if (!match) continue;

            const mins = parseInt(match[1], 10);
            const secs = parseInt(match[2], 10);
            const ms = match[3] ? parseInt(match[3].padEnd(3, '0'), 10) : 0;
            const time = mins * 60 + secs + ms / 1000;
            const text = match[4].trim();

            lines.push({ time, text });
        }

        // Sort by time
        lines.sort((a, b) => a.time - b.time);
        return lines;
    },

    /**
     * Clean title — strip YouTube-style suffixes
     */
    _cleanTitle(title) {
        if (!title) return '';
        return title
            .replace(/\s*[\(\[]\s*(Official\s*)?(Music\s*)?(Video|Audio|Lyric|Lyrics|Visualizer|MV|HQ|HD|4K|Live|Remix|Version|Remaster|Remastered|Explicit)\s*[\)\]]/gi, '')
            .replace(/\s*[\(\[]\s*feat\.?\s+[^\)\]]+[\)\]]/gi, '')
            .replace(/\s*\|\s*.+$/, '')
            .replace(/\s{2,}/g, ' ')
            .trim();
    },

    /**
     * Sync lyrics to current playback time using binary search
     */
    _syncToTime(currentTime) {
        if (!this._lines.length) return;

        const idx = this._findActiveLine(currentTime);
        if (idx === this._activeLine) return;

        this._activeLine = idx;

        // Update line classes
        const lineEls = this._container?.querySelectorAll('.lyrics-line');
        if (!lineEls) return;

        for (let i = 0; i < lineEls.length; i++) {
            lineEls[i].classList.remove('lyrics-line--active', 'lyrics-line--past', 'lyrics-line--future');

            if (i === idx) {
                lineEls[i].classList.add('lyrics-line--active');
            } else if (i < idx) {
                lineEls[i].classList.add('lyrics-line--past');
            } else {
                lineEls[i].classList.add('lyrics-line--future');
            }
        }

        this._scrollToActive();
    },

    /**
     * Binary search for the active line index
     */
    _findActiveLine(time) {
        const lines = this._lines;
        if (!lines.length) return -1;
        if (time < lines[0].time) return -1;

        let lo = 0;
        let hi = lines.length - 1;

        while (lo <= hi) {
            const mid = (lo + hi) >>> 1;
            if (lines[mid].time <= time) {
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }

        return hi;
    },

    /**
     * Scroll the active lyric line to center of the container
     */
    _scrollToActive() {
        if (this._userScrolling) return;

        const scroll = document.getElementById('lyricsScroll');
        const activeEl = this._container?.querySelector('.lyrics-line--active');
        if (!scroll || !activeEl) return;

        const scrollRect = scroll.getBoundingClientRect();
        const activeRect = activeEl.getBoundingClientRect();
        const offset = activeRect.top - scrollRect.top - (scrollRect.height / 2) + (activeRect.height / 2);

        scroll.scrollBy({ top: offset, behavior: 'smooth' });
    },

    /**
     * Render synced lyrics lines into the container
     */
    _renderLyrics() {
        if (!this._container) return;

        let html = '<div class="lyrics-lines">';
        for (let i = 0; i < this._lines.length; i++) {
            const line = this._lines[i];
            const text = line.text || '♪';
            const cls = i === 0 ? 'lyrics-line lyrics-line--future' : 'lyrics-line lyrics-line--future';
            html += `<div class="${cls}" data-index="${i}" data-time="${line.time}">${UI.escapeHtml(text)}</div>`;
        }
        html += '</div>';

        this._container.innerHTML = html;

        // Add click-to-seek handlers
        const lineEls = this._container.querySelectorAll('.lyrics-line');
        lineEls.forEach(el => {
            el.addEventListener('click', () => {
                const time = parseFloat(el.dataset.time);
                if (Player.audio && Number.isFinite(time)) {
                    Player.audio.currentTime = time;
                    this._userScrolling = false;
                }
            });
        });
    },

    /**
     * Render plain (unsynced) lyrics
     */
    _renderPlain(text) {
        if (!this._container) return;

        this._container.innerHTML = `
            <div class="lyrics-plain">
                <div class="lyrics-plain__note">
                    <i class="fas fa-info-circle"></i> Synced lyrics not available
                </div>
                <div class="lyrics-plain__text">${UI.escapeHtml(text)}</div>
            </div>
        `;
    },

    /**
     * Render loading state
     */
    _renderLoading() {
        if (!this._container) return;

        this._container.innerHTML = `
            <div class="lyrics-loading">
                <div class="lyrics-loading__pulse"></div>
                <div class="lyrics-loading__pulse"></div>
                <div class="lyrics-loading__pulse"></div>
            </div>
        `;
    },

    /**
     * Render empty / no lyrics found state
     */
    _renderEmpty() {
        if (!this._container) return;

        this._container.innerHTML = `
            <div class="lyrics-empty">
                <i class="fas fa-music lyrics-empty__icon"></i>
                <div class="lyrics-empty__text">No lyrics available</div>
            </div>
        `;
    },
};

// ─── Inject styles ──────────────────────────────────────────────────────────

(function injectLyricsStyles() {
    const style = document.createElement('style');
    style.id = 'lyricsStyles';
    style.textContent = `
        /* ─── Lyrics Panel ─────────────────────────────────────────── */

        .lyrics-panel {
            position: fixed;
            inset: 0;
            z-index: 10000;
            display: flex;
            flex-direction: column;
            transform: translateY(100%);
            transition: transform 0.4s cubic-bezier(0.22, 1, 0.36, 1);
            will-change: transform;
        }

        .lyrics-panel.open {
            transform: translateY(0);
        }

        .lyrics-panel__backdrop {
            position: absolute;
            inset: 0;
            background-size: cover;
            background-position: center;
            filter: blur(60px) saturate(1.5);
            transform: scale(1.3);
            z-index: 0;
        }

        .lyrics-panel__backdrop::after {
            content: '';
            position: absolute;
            inset: 0;
            background: rgba(0, 0, 0, 0.65);
        }

        /* Header */
        .lyrics-panel__header {
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 16px 20px;
            padding-top: max(16px, env(safe-area-inset-top));
            flex-shrink: 0;
        }

        .lyrics-panel__close {
            width: 36px;
            height: 36px;
            border: none;
            background: rgba(255,255,255,0.15);
            border-radius: 50%;
            color: #fff;
            font-size: 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            -webkit-tap-highlight-color: transparent;
        }

        .lyrics-panel__close:active {
            background: rgba(255,255,255,0.25);
        }

        .lyrics-panel__track-info {
            min-width: 0;
        }

        .lyrics-panel__title {
            font-size: 16px;
            font-weight: 700;
            color: #fff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .lyrics-panel__artist {
            font-size: 13px;
            color: rgba(255,255,255,0.6);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        /* Body */
        .lyrics-panel__body {
            position: relative;
            z-index: 1;
            flex: 1;
            min-height: 0;
            display: flex;
            flex-direction: column;
        }

        .lyrics-panel__scroll {
            flex: 1;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
            padding: 0 24px;
            scroll-behavior: auto;
            mask-image: linear-gradient(to bottom,
                transparent 0%, black 10%, black 90%, transparent 100%);
            -webkit-mask-image: linear-gradient(to bottom,
                transparent 0%, black 10%, black 90%, transparent 100%);
        }

        .lyrics-panel__content {
            padding: 30vh 0;
        }

        /* Synced lines */
        .lyrics-lines {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .lyrics-line {
            font-size: 22px;
            font-weight: 600;
            line-height: 1.4;
            color: rgba(255,255,255,0.5);
            cursor: pointer;
            transition: color 0.3s ease, opacity 0.3s ease, transform 0.3s ease, font-size 0.3s ease;
            -webkit-tap-highlight-color: transparent;
            user-select: none;
        }

        .lyrics-line--active {
            color: #fff;
            font-size: 28px;
            font-weight: 800;
            opacity: 1;
            transform: scale(1);
        }

        .lyrics-line--past {
            color: rgba(255,255,255,0.35);
            font-size: 22px;
        }

        .lyrics-line--future {
            color: rgba(255,255,255,0.5);
            font-size: 22px;
        }

        .lyrics-line:active {
            opacity: 0.7;
        }

        /* Plain lyrics */
        .lyrics-plain {
            padding: 20px 0;
        }

        .lyrics-plain__note {
            font-size: 13px;
            color: rgba(255,255,255,0.45);
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .lyrics-plain__text {
            font-size: 18px;
            line-height: 1.8;
            color: rgba(255,255,255,0.75);
            white-space: pre-wrap;
            word-break: break-word;
        }

        /* Loading */
        .lyrics-loading {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 12px;
            padding: 60px 0;
        }

        .lyrics-loading__pulse {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: rgba(255,255,255,0.5);
            animation: lyricsPulse 1.4s ease-in-out infinite;
        }

        .lyrics-loading__pulse:nth-child(2) {
            animation-delay: 0.2s;
        }

        .lyrics-loading__pulse:nth-child(3) {
            animation-delay: 0.4s;
        }

        @keyframes lyricsPulse {
            0%, 80%, 100% { transform: scale(0.6); opacity: 0.3; }
            40% { transform: scale(1); opacity: 1; }
        }

        /* Empty */
        .lyrics-empty {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 16px;
            padding: 60px 0;
            color: rgba(255,255,255,0.4);
        }

        .lyrics-empty__icon {
            font-size: 48px;
        }

        .lyrics-empty__text {
            font-size: 16px;
            font-weight: 500;
        }
    `;
    document.head.appendChild(style);
})();

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => Lyrics.init());
