/* SuperBot PWA service worker.
 *
 * Strategy: cache the app shell (static JS/CSS/HTML/icons) so the app
 * installs and opens instantly, but NEVER cache API responses (/api/*)
 * -- this is a live trading dashboard, stale prices/positions/PnL would
 * be actively misleading, so every API call always goes to the network.
 */
const CACHE_NAME = 'superbot-shell-v1';
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
      // Stale-while-revalidate for the app shell: serve cached immediately
      // if present, update cache in background.
      return cached || networkFetch;
    })
  );
});
