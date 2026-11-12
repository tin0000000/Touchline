const CACHE_NAME = 'touchline-v42';
const APP_SHELL = ['./', './index.html', './manifest.webmanifest', './icons/touchline.svg', './assets/kit-flat-template.png', './assets/shirt-front-template.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.pathname.startsWith('/api/')) return;
  const isAppDocument = request.mode === 'navigate' || url.pathname.endsWith('/index.html');
  if (isAppDocument) {
    const latestUrl = new URL(request.url);
    latestUrl.searchParams.set('__touchline_cache', CACHE_NAME);
    event.respondWith(fetch(latestUrl.toString(), { cache: 'no-store', credentials: request.credentials }).then(response => {
      if (response.ok && url.origin === self.location.origin) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
      }
      return response;
    }).catch(() => caches.match(request).then(cached => cached || caches.match('./index.html'))));
    return;
  }
  event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
    if (response.ok && url.origin === self.location.origin) {
      const copy = response.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
    }
    return response;
  }).catch(() => caches.match('./index.html'))));
});
