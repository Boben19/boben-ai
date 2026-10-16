/* Boben service worker
 *
 * - On install: saves the "app shell" (page + CSS + JS + icons + Bootstrap) in the cache.
 * - Pages:   try the network first (fresh), fall back to the cached copy when offline.
 * - Static:  use the cache first (fast), update it quietly in the background.
 * - /api/:   NEVER cached. New replies always need the internet.
 * - /accounts/ (sign-in, profile, OAuth): NEVER cached, and a redirect to the sign-in page is never
 *   stored as the home page. Signing out also deletes this cache (see auth.js).
 *
 * Bump CACHE_VERSION whenever you change cached files so old caches get deleted.
 */
const CACHE_VERSION = "v6";
const CACHE_NAME = "boben-" + CACHE_VERSION;

// These paths must match STATIC_URL ("/static/") in config/settings.py.
const APP_SHELL = [
  "/offline/",
  "/manifest.json",
  "/static/assistant/css/style.css",
  "/static/assistant/js/app.js",
  "/static/assistant/js/emoji-bg.js",
  "/static/assistant/js/auth.js",
  "/static/assistant/icons/icon-192.png",
  "/static/assistant/icons/icon-512.png",
  "/static/assistant/icons/icon-maskable-512.png",
  "/static/assistant/icons/apple-touch-icon.png",
  "/static/assistant/icons/favicon-64.png",
];

// Bootstrap comes from a CDN, so we store it too (otherwise the page looks unstyled offline).
const CDN_FILES = [
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      await cache.addAll(APP_SHELL);
      // CDN files are "nice to have": if one fails, the install still succeeds.
      await Promise.allSettled(
        CDN_FILES.map((url) => cache.add(new Request(url, { mode: "no-cors" })))
      );
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("boben") && k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Only handle GET requests. Chat messages (POST) and /api/ go straight to the network.
  if (request.method !== "GET") return;
  if (url.origin === self.location.origin && (url.pathname.startsWith("/api/") || url.pathname.startsWith("/accounts/"))) return;

  // Page navigations: network first, then cache, then the offline page.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Only keep the real chat page (a signed-in 200). If the server sent us to the sign-in page, response.redirected is true.
          if (response.ok && !response.redirected && url.origin === self.location.origin && (url.pathname === "/" || url.pathname === "/offline/")) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request, { ignoreSearch: true });
          // The whole app is one page, so the cached home page is the best fallback.
          return cached || (await caches.match("/")) || (await caches.match("/offline/"));
        })
    );
    return;
  }

  // Static files, manifest, and CDN files: cache first, refresh in the background.
  const sameOriginAsset = url.origin === self.location.origin &&
    (url.pathname.startsWith("/static/") || url.pathname === "/manifest.json");
  const knownCdn = CDN_FILES.includes(request.url);

  if (sameOriginAsset || knownCdn) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const refresh = fetch(request)
          .then((response) => {
            if (response && (response.ok || response.type === "opaque")) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
            }
            return response;
          })
          .catch(() => cached);
        return cached || refresh;
      })
    );
  }
});
