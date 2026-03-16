/* ══════════════════════════════════════════════════════════════
   Setlist CMDR — Service Worker
   Caches the app shell so the UI loads instantly even before
   the Pi's WiFi hotspot is fully up. Live sync still needs
   the server — only the interface assets are cached.
   ══════════════════════════════════════════════════════════════ */

const CACHE = 'cmdr-v1';

// Everything needed to render the UI without a network round-trip
const SHELL = [
  '/',
  '/leader',
  '/static/leader.css',
  '/static/img/logo_large.png',
  '/static/img/logo_top_right.png',
  '/static/img/logo_bottom_left.png',
  '/static/img/logo_bottom_right_wide.png',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/img/apple-touch-icon.png',
];

// ── Install: pre-cache the shell ──────────────────────────────
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: remove old caches ───────────────────────────────
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// ── Fetch: cache-first for shell assets, network-first for API ─
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Never cache API calls, WebSockets, or external resources
  if (
    url.pathname.startsWith('/api/') ||
    url.protocol === 'ws:' ||
    url.protocol === 'wss:' ||
    url.hostname !== self.location.hostname
  ) {
    return; // fall through to normal network fetch
  }

  // Cache-first for shell assets
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      // Not in cache — fetch, cache, return
      return fetch(e.request).then(resp => {
        if (!resp || resp.status !== 200 || resp.type !== 'basic') return resp;
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return resp;
      });
    })
  );
});
