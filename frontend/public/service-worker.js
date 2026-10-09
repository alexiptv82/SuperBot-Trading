/* SuperBot PWA service worker.
 *
 * Strategy: cache the app shell so the app installs and still opens offline,
 * but NEVER cache API responses (/api/*) -- this is a live trading dashboard,
 * stale prices/positions/PnL would be actively misleading, so every API call
 * always goes to the network.
 *
 * Pages (navigations) are NETWORK-FIRST: after a deploy the very next launch
 * gets the new index.html (and so the new JS bundle). The previous
 * stale-while-revalidate behaviour served the OLD page first, so a fix could
 * take several launches to reach the phone. The cached copy is only a
 * fallback for when the network is unreachable.
 */
const CACHE_NAME = 'superbot-shell-v2';
const APP_SHELL = ['/', '/manifest.json', '/icons/icon-192.png', '/icons/icon-512.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Never intercept API calls -- always hit the network for live data.
  if (url.pathname.startsWith('/api/')) return;

  // Cross-origin requests (e.g. the backend on a different host:port) --
  // let the browser handle them normally, don't try to cache.
  if (url.origin !== self.location.origin) return;

  // Page loads: network first, cached copy only when offline. `no-cache`
  // makes the browser revalidate with the server instead of reusing an HTTP
  // cache copy of index.html that is still "fresh" by heuristic.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request.url, { cache: 'no-cache' })
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put('/', copy));
          }
          return response;
        })
        .catch(() => caches.match('/'))
    );
    return;
  }

  // Build output (/static/...) has a content hash in its name, so a cached
  // copy is always valid: cache first. Never store an HTML response under a
  // JS/CSS URL (the server answers a missing file with the SPA's index.html).
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          const type = (response && response.headers.get('content-type')) || '';
          if (response && response.ok && !type.includes('text/html')) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        });
      })
    );
    return;
  }

  // Everything else (manifest, icons): serve cached immediately if present
  // and refresh the cache in the background.
  event.respondWith(
    caches.match(request).then((cached) => {
      const networkFetch = fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || networkFetch;
    })
  );
});
