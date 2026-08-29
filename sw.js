// Bump this whenever index.html/manifest/icons change so clients
// pick up the new files instead of stale cached ones.
const CACHE_NAME = "cocoa-calc-v11";

const APP_SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/icon-512-maskable.png",
];

// Cache the app shell as soon as the service worker installs.
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

// Clear out old caches from previous versions.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);

  // Never intercept the market-price serverless function — it returns
  // live data, so it must always hit the network, never the cache.
  // Letting the browser handle it directly (no respondWith) also means
  // it correctly fails/rejects when offline instead of silently
  // replaying a stale cached price.
  if (url.pathname.startsWith("/.netlify/functions/")) return;

  // Cache-first for the static app shell, with a network fallback
  // (and cache top-up) for anything else same-origin.
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;

      return fetch(event.request)
        .then((response) => {
          if (response && response.status === 200 && response.type === "basic") {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => {
          // Offline and not cached: fall back to the app shell for
          // navigation requests so the app still opens.
          if (event.request.mode === "navigate") {
            return caches.match("/index.html");
          }
        });
    })
  );
});
