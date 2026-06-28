// Service worker simples: deixa o app abrir mesmo sem internet (casca offline).
// Os DADOS (index.json e dias/*.json) sao sempre buscados frescos (no-store).
const CACHE = 'serventia-bj-v1';
const CASCA = ['index.html', 'manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CASCA)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // dados sempre pela rede (atualizados todo dia); se falhar, tenta cache
  if (url.pathname.endsWith('.json')) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  // casca do app: cache primeiro
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
