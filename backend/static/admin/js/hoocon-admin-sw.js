/**
 * Admin PWA service worker — Web Push only (no Workbox precache).
 * Served at /admin/sw.js with scope /admin/ so iOS home-screen Admin can subscribe.
 */
/* eslint-disable no-restricted-globals */
self.addEventListener("install", function (event) {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", function (event) {
  var data = {
    title: "Hoocon Admin",
    body: "Новое уведомление",
    url: "/admin/",
    tag: "hoocon-admin",
  };
  try {
    if (event.data) {
      var parsed = event.data.json();
      data = Object.assign(data, parsed);
    }
  } catch (_err) {
    try {
      var text = event.data && event.data.text();
      if (text) data.body = String(text).slice(0, 240);
    } catch (_err2) {
      /* keep defaults */
    }
  }
  var title = String(data.title || "Hoocon Admin").slice(0, 120);
  var options = {
    body: String(data.body || "").slice(0, 240),
    icon: "/static/admin/img/pwa-admin-192.png",
    badge: "/static/admin/img/pwa-admin-192.png",
    tag: data.tag || "hoocon-admin",
    data: { url: data.url || "/admin/" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var raw = event.notification.data && event.notification.data.url;
  var target = safeAdminPath(raw);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (all) {
      for (var i = 0; i < all.length; i += 1) {
        var client = all[i];
        if ("focus" in client) {
          return client.focus().then(function (focused) {
            if (focused && "navigate" in focused) {
              return focused.navigate(target);
            }
          });
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(target);
      }
    }),
  );
});

/** Same-origin Admin path only. */
function safeAdminPath(raw) {
  if (typeof raw !== "string") return "/admin/";
  var url = raw.trim() || "/admin/";
  if (!url.startsWith("/") || url.startsWith("//") || url.indexOf("://") !== -1) {
    return "/admin/";
  }
  return url.slice(0, 500);
}
