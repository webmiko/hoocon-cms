/// <reference lib="webworker" />
/**
 * Custom service worker: Workbox precache + Web Push handlers.
 * Built via vite-plugin-pwa injectManifest (prod only).
 *
 * Intentionally no navigateFallback to index.html (Django spa_index SSR).
 */
import { clientsClaim } from "workbox-core";
import { cleanupOutdatedCaches, precacheAndRoute } from "workbox-precaching";

declare let self: ServiceWorkerGlobalScope;

void self.skipWaiting();
clientsClaim();

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

type PushPayload = {
  title?: string;
  body?: string;
  url?: string;
  tag?: string;
};

self.addEventListener("push", (event: PushEvent) => {
  let data: PushPayload = {
    title: "Hoocon",
    body: "Новое уведомление",
    url: "/",
    tag: "hoocon",
  };
  try {
    if (event.data) {
      const parsed = event.data.json() as PushPayload;
      data = { ...data, ...parsed };
    }
  } catch {
    try {
      const text = event.data?.text();
      if (text) data.body = text.slice(0, 240);
    } catch {
      /* keep defaults */
    }
  }
  const title = (data.title || "Hoocon").slice(0, 120);
  const options: NotificationOptions = {
    body: (data.body || "").slice(0, 240),
    icon: "/pwa-192.png",
    badge: "/pwa-192.png",
    tag: data.tag || "hoocon",
    data: { url: data.url || "/" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event: NotificationEvent) => {
  event.notification.close();
  const raw = (event.notification.data as { url?: string } | undefined)?.url;
  const target = typeof raw === "string" && raw.startsWith("/") ? raw : "/";
  event.waitUntil(
    (async () => {
      const all = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      for (const client of all) {
        if ("focus" in client) {
          await client.focus();
          if ("navigate" in client) {
            await (client as WindowClient).navigate(target);
          }
          return;
        }
      }
      await self.clients.openWindow(target);
    })(),
  );
});
