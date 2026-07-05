// PWA: Service-Worker-Registrierung.
// navigator.serviceWorker existiert nur in einem Secure Context (HTTPS oder
// localhost) – über http://<LAN-IP> wird hier also einfach nichts registriert
// und die App läuft als normale Website weiter.
(function () {
    if (!('serviceWorker' in navigator)) return;
    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js').catch(function (err) {
            console.warn('Service Worker nicht registriert:', err);
        });
    });
})();
