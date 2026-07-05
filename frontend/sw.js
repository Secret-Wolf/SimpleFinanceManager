// Service Worker des Finanzmanagers.
//
// Strategie: Netz zuerst, Cache nur als Offline-Fallback. Dadurch gibt es nach
// einem Deploy nie veraltete JS/CSS-Stände (das war die Bedingung, überhaupt
// einen Service Worker einzusetzen). /api/* wird bewusst NICHT abgefangen:
// Finanzdaten und Auth-Cookies gehören nicht in den Cache.
//
// Wird unter /sw.js ausgeliefert (SPA-Catch-all in backend/app/main.py serviert
// Dateien aus frontend/ an der Wurzel), damit der Scope die ganze App umfasst.

const CACHE_NAME = 'finanzmanager-shell-v1';

// App-Shell, damit ein Offline-Start zumindest die Oberfläche lädt.
// Best effort: ein fehlender Eintrag darf die Installation nicht verhindern.
const SHELL_ASSETS = [
    '/',
    '/manifest.json',
    '/static/css/style.css',
    '/static/fonts/inter-latin.woff2',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
    '/static/js/event-handlers.js',
    '/static/js/api.js',
    '/static/js/utils.js',
    '/static/js/transactions.js',
    '/static/js/categories.js',
    '/static/js/rules.js',
    '/static/js/import.js',
    '/static/js/statistics.js',
    '/static/js/accounts.js',
    '/static/js/users.js',
    '/static/js/households.js',
    '/static/js/banking.js',
    '/static/js/app.js',
    '/static/js/auth.js',
    '/static/js/pwa.js'
];

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE_NAME);
        await Promise.allSettled(SHELL_ASSETS.map((url) => cache.add(url)));
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const keys = await caches.keys();
        await Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)));
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;
    if (url.pathname.startsWith('/api/')) return; // API immer live, nie cachen

    event.respondWith(networkFirst(request));
});

async function networkFirst(request) {
    const cache = await caches.open(CACHE_NAME);
    try {
        const response = await fetch(request);
        if (response && response.ok) {
            cache.put(request, response.clone());
        }
        return response;
    } catch (err) {
        const cached = await cache.match(request, { ignoreSearch: request.mode === 'navigate' });
        if (cached) return cached;
        if (request.mode === 'navigate') {
            // SPA-Fallback: jede Navigation landet auf der App-Shell
            const shell = await cache.match('/');
            if (shell) return shell;
        }
        throw err;
    }
}
