// Genesis AI Assistant - Service Worker
// Provides offline caching and background sync capabilities

const CACHE_VERSION = 'genesis-v1';
const CACHE_NAME = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

// Assets to pre-cache on install
const PRECACHE_ASSETS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/shortcuts.js',
  '/static/offline.html',
  '/static/vendor/marked.min.js',
  '/static/vendor/purify.min.js',
  '/static/vendor/highlight.min.js',
  '/static/vendor/github.min.css',
  '/static/vendor/github-dark.min.css'
];

// API endpoints to cache with network-first strategy
const API_CACHE_PATTERNS = [
  '/api/status',
  '/api/metrics',
  '/api/conversation',
  '/api/messages/search',
  '/api/personas',
  '/api/notifications'
];

// Install event: pre-cache static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Install event');

  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Pre-caching static assets');
        return cache.addAll(PRECACHE_ASSETS.map(url => new Request(url, { cache: 'reload' })));
      })
      .then(() => self.skipWaiting()) // Activate immediately
  );
});

// Activate event: clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activate event');

  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => name.startsWith('genesis-') && name !== CACHE_NAME && name !== RUNTIME_CACHE)
            .map((name) => {
              console.log('[SW] Deleting old cache:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => self.clients.claim()) // Take control of all pages
  );
});

// Fetch event: implement caching strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Skip chrome-extension and other non-http(s) requests
  if (!url.protocol.startsWith('http')) {
    return;
  }

  // API requests: network-first with fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(request));
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/') || PRECACHE_ASSETS.includes(url.pathname)) {
    event.respondWith(cacheFirstStrategy(request));
    return;
  }

  // Default: network-first for HTML
  event.respondWith(networkFirstStrategy(request));
});

// Cache-first strategy (for static assets)
async function cacheFirstStrategy(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  if (cached) {
    console.log('[SW] Cache hit:', request.url);
    return cached;
  }

  try {
    const response = await fetch(request);

    // Cache successful responses
    if (response.ok) {
      cache.put(request, response.clone());
    }

    return response;
  } catch (error) {
    console.error('[SW] Fetch failed:', request.url, error);

    // Return offline page for navigation requests
    if (request.mode === 'navigate') {
      const offlinePage = await cache.match('/static/offline.html');
      if (offlinePage) {
        return offlinePage;
      }
    }

    throw error;
  }
}

// Network-first strategy (for API and dynamic content)
async function networkFirstStrategy(request) {
  const cache = await caches.open(RUNTIME_CACHE);

  try {
    const response = await fetch(request);

    // Cache successful responses
    if (response.ok) {
      cache.put(request, response.clone());
    }

    return response;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', request.url);
    const cached = await cache.match(request);

    if (cached) {
      return cached;
    }

    // Return offline page for navigation requests
    if (request.mode === 'navigate') {
      const offlineCache = await caches.open(CACHE_NAME);
      const offlinePage = await offlineCache.match('/static/offline.html');
      if (offlinePage) {
        return offlinePage;
      }
    }

    throw error;
  }
}

// Push notification event
self.addEventListener('push', (event) => {
  console.log('[SW] Push notification received');

  let data = {
    title: 'Genesis',
    body: 'You have a new notification',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-72x72.png',
    tag: 'genesis-notification',
    requireInteraction: false
  };

  if (event.data) {
    try {
      const payload = event.data.json();
      data = { ...data, ...payload };
    } catch (e) {
      data.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon,
      badge: data.badge,
      tag: data.tag,
      requireInteraction: data.requireInteraction,
      data: data.data || {}
    })
  );
});

// Notification click event
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked');

  event.notification.close();

  const urlToOpen = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Check if there's already a window open
        for (const client of clientList) {
          if (client.url === urlToOpen && 'focus' in client) {
            return client.focus();
          }
        }

        // Open a new window
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

// Background sync event (for future use)
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);

  if (event.tag === 'sync-messages') {
    event.waitUntil(syncMessages());
  }
});

async function syncMessages() {
  // Placeholder for future background sync implementation
  console.log('[SW] Syncing messages...');
}

// Message event (communicate with main app)
self.addEventListener('message', (event) => {
  console.log('[SW] Message received:', event.data);

  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }

  if (event.data && event.data.type === 'CACHE_URLS') {
    const urls = event.data.urls || [];
    event.waitUntil(
      caches.open(RUNTIME_CACHE).then((cache) => cache.addAll(urls))
    );
  }
});
