/* ══════════════════════════════════════════════════════════════
   Setlist CMDR — Service Worker

   Cache strategy:
   - HTML pages (/ and /leader): network-first.
     Always fetch fresh when online. Cache is fallback only
     for when the Pi hotspot is slow to come up.
   - Static assets (CSS, images): cache-first with BUILD_ID
     versioning. The server injects the build ID into every CSS
     URL so a new deploy gets a new URL, bypassing cache.
   - API calls and WebSockets: never cached, always network.

   Cache invalidation:
   Cache is named cmdr-{BUILD_ID}. BUILD_ID is a hash of the
   source files computed at server startup, served via
   /api/version. When files change the SW installs a new named
   cache and the activate step deletes all old cmdr-* caches.
   ══════════════════════════════════════════════════════════════ */

const FALLBACK_CACHE = 'cmdr-init';
let CACHE = FALLBACK_CACHE;

const PRECACHE = [
  '/static/leader.css',
  '/static/img/logo_large.png',
  '/static/img/logo_top_right.png',
  '/static/img/logo_bottom_left.png',
  '/static/img/logo_bottom_right_wide.png',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/img/apple-touch-icon.png',
  '/static/manifest-leader.json',
  '/static/manifest-musician.json',
];

self.addEventListener('install', e => {
  e.waitUntil(
    fetch('/api/version')
      .then(r => r.json())
      .then(data => {
        CACHE = 'cmdr-' + data.build;
        return caches.open(CACHE).then(c => c.addAll(PRECACHE));
      })
      .catch(() => Promise.resolve())
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    fetch('/api/version')
      .then(r => r.json())
      .then(data => { CACHE = 'cmdr-' + data.build; })
      .catch(() => {})
      .then(() =>
        caches.keys().then(keys =>
          Promise.all(
            keys
              .filter(k => k !== CACHE && k.startsWith('cmdr-'))
              .map(k => caches.delete(k))
          )
        )
      )
      .then(() => self.clients.claim())
      .then(() =>
        self.clients.matchAll({ type: 'window' }).then(clients =>
          clients.forEach(c => c.postMessage({ type: 'sw_updated' }))
        )
      )
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  if (
    e.request.method !== 'GET' ||
    url.pathname.startsWith('/api/') ||
    url.protocol === 'ws:' ||
    url.protocol === 'wss:' ||
    url.hostname !== self.location.hostname
  ) {
    return;
  }

  // HTML: network-first, cache as offline fallback
  if (url.pathname === '/' || url.pathname === '/leader') {
    e.respondWith(
      fetch(e.request)
        .then(resp => {
          if (resp.ok) {
            caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
          }
          return resp;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Static assets: cache-first (versioned URLs auto-bust)
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(resp => {
        if (resp && resp.status === 200 && resp.type === 'basic') {
          caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
        }
        return resp;
      });
    })
  );
});
