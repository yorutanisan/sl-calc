// 中身を更新したら CACHE の番号を上げる（スマホ側が新しい版に切り替わる）
const CACHE = 'slcalc-v3';
const FILES = ['./', 'index.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'icon-maskable-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  // ランキングとテクニカルは常に最新を取りに行き、圏外のときだけ前回の分を出す
  const url = new URL(e.request.url);
  if (url.pathname.endsWith('/ranking.json') || url.pathname.includes('/tech/')) {
    url.search = '';
    e.respondWith(fetch(e.request).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(url.href, copy)); }
      return r;
    }).catch(() => caches.match(url.href)));
    return;
  }
  e.respondWith(caches.match(e.request, {ignoreSearch: true}).then(r => r || fetch(e.request)));
});
