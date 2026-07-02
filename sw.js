// KILL-SWITCH: este service worker se auto-remove e limpa todos os caches.
// (Os SWs antigos presos nos celulares serao substituidos por este e sumirao.)
self.addEventListener('install', e => { self.skipWaiting(); });
self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    try { const ks = await caches.keys(); await Promise.all(ks.map(k => caches.delete(k))); } catch (_) {}
    try { await self.registration.unregister(); } catch (_) {}
    try {
      const cs = await self.clients.matchAll({ type: 'window' });
      cs.forEach(c => c.navigate(c.url));   // recarrega as janelas abertas ja SEM o SW
    } catch (_) {}
  })());
});
// sem handler de fetch: tudo vai direto para a rede
