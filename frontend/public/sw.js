/* Mandi Mitra service worker — offline-first status caching */
const CACHE = 'mandi-mitra-v1';
const STATUS_CACHE = 'mm-status-cache';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // Cache last-known farmer status and queue snapshots for offline access.
  if (event.request.method === 'GET' && url.pathname.startsWith('/api/farmer/status')) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(STATUS_CACHE).then((c) => c.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request).then((hit) => hit || new Response(
          JSON.stringify({ offline: true, message: 'Offline: showing last synced status' }),
          { headers: { 'Content-Type': 'application/json' } }
        )))
    );
    return;
  }
  // Network-first for other API GETs, cache fallback.
  if (event.request.method === 'GET' && url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
  }
});
