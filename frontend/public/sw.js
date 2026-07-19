/* Kuantile service worker.
   Strateji: /api asla önbelleklenmez; gezinmeler network-first (deploy sonrası
   bayat kabuk kalmasın), hash'li statik varlıklar cache-first. */

const VERSION = "kt-v1";
const CORE = ["/", "/manifest.webmanifest", "/logo.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(CORE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // canlı veri, asla önbellekten

  // Gezinme: önce ağ, düşerse önbellekteki kabuk
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match("/"))),
    );
    return;
  }

  // Hash'li varlıklar ve görseller: önce önbellek
  e.respondWith(
    caches.match(req).then((hit) =>
      hit ||
      fetch(req).then((res) => {
        if (res.ok && (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/icons/") || url.pathname === "/logo.png")) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
        }
        return res;
      }),
    ),
  );
});
