// Registers the service worker that makes SuperBot installable as a PWA.
// Only runs in production builds, and only over HTTPS or on localhost
// (service workers require a secure context).
export function register() {
  if (process.env.NODE_ENV !== 'production') return;
  if (!('serviceWorker' in navigator)) return;

  window.addEventListener('load', () => {
    const swUrl = `${process.env.PUBLIC_URL || ''}/service-worker.js`;
    navigator.serviceWorker
      .register(swUrl)
      .catch((err) => console.warn('Service worker registration failed:', err));
  });
}

export function unregister() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.ready
    .then((registration) => registration.unregister())
    .catch(() => {});
}
