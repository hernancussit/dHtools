// dHtools - Progressive Web App Service Worker (v2.0.0 - Web Push & Notifications)
const CACHE_NAME = 'dhtools-cache-v2.0.0';

const ASSETS_TO_CACHE = [
  '/',
  '/wiki',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Pass API requests directly to network without caching
  if (event.request.url.includes('/api/')) {
    return;
  }
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});

// ==================== WEB PUSH & NATIVE NOTIFICATIONS ====================

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'dHtools', body: event.data ? event.data.text() : 'Notificación de dHtools' };
  }
  const title = data.title || 'dHtools';
  const options = {
    body: data.body || 'Tu descarga ha finalizado.',
    icon: data.icon || '/static/icons/icon-192.png',
    badge: data.badge || '/static/icons/icon-192.png',
    vibrate: data.vibrate || [150, 50, 150],
    data: data.data || { url: '/' },
    actions: data.actions || [
      { action: 'open', title: '📂 Abrir' },
      { action: 'close', title: '✕ Cerrar' }
    ],
    tag: data.tag || ('dhtools-notif-' + Date.now()),
    renotify: true
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action === 'close') return;

  const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          if ('navigate' in client && targetUrl && targetUrl !== '/') {
            client.navigate(targetUrl);
          }
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SHOW_NOTIFICATION') {
    const { title, options } = event.data;
    event.waitUntil(self.registration.showNotification(title, options));
  }
});
