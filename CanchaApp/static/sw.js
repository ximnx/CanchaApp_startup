/* Service Worker de Ready Match (PWA instalable y notificaciones) */

const CACHE_NOMBRE = "ready-match-v4";
const ARCHIVOS_BASE = [
    "/static/style.css",
    "/static/pwa.js",
    "/static/imagenes/logo_ready_match.png",
    "/static/imagenes/icon-192.png",
    "/static/imagenes/icon-512.png"
];

self.addEventListener("install", function (evento) {
    evento.waitUntil(
        caches.open(CACHE_NOMBRE).then(function (cache) {
            return cache.addAll(ARCHIVOS_BASE);
        })
    );
    self.skipWaiting();
});

self.addEventListener("activate", function (evento) {
    evento.waitUntil(
        caches.keys().then(function (claves) {
            return Promise.all(
                claves
                    .filter(function (clave) { return clave !== CACHE_NOMBRE; })
                    .map(function (clave) { return caches.delete(clave); })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener("fetch", function (evento) {
    if (evento.request.method !== "GET") return;
    evento.respondWith(
        fetch(evento.request).catch(function () {
            return caches.match(evento.request);
        })
    );
});

self.addEventListener("notificationclick", function (evento) {
    evento.notification.close();
    const rutaDestino = (evento.notification.data && evento.notification.data.url) || "/";

    evento.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (ventanas) {
            for (let i = 0; i < ventanas.length; i++) {
                const ventana = ventanas[i];
                if ("focus" in ventana) {
                    ventana.navigate(rutaDestino);
                    return ventana.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(rutaDestino);
            }
        })
    );
});
