/**
 * Admin: enable support-chat Web Push for the logged-in staff user.
 * Loaded on support conversation changelist.
 */
(function () {
  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = window.atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) {
      output[i] = raw.charCodeAt(i);
    }
    return output;
  }

  async function enablePush() {
    const status = document.getElementById("hoocon-webpush-status");
    function setStatus(text) {
      if (status) status.textContent = text;
    }
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        setStatus("Браузер не поддерживает Web Push");
        return;
      }
      try {
        // Admin is outside the SPA shell — ensure the PWA SW is registered.
        let reg = await navigator.serviceWorker.getRegistration("/");
        if (!reg) {
          reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
          await navigator.serviceWorker.ready;
        }
        const meta = await fetch("/api/webpush/vapid-public-key/").then((r) => r.json());
        if (!meta.configured || !meta.public_key) {
          setStatus("VAPID не настроен на сервере");
          return;
        }
        const perm = await Notification.requestPermission();
        if (perm !== "granted") {
          setStatus("Нужно разрешение уведомлений");
          return;
        }
        reg = await navigator.serviceWorker.ready;
        let sub = await reg.pushManager.getSubscription();
        if (!sub) {
          sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(meta.public_key),
          });
        }
      const json = sub.toJSON();
      const resp = await fetch("/api/webpush/subscribe/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({
          endpoint: json.endpoint,
          keys: json.keys,
          topic_support: true,
        }),
      });
      if (!resp.ok) {
        setStatus("Ошибка подписки (" + resp.status + ")");
        return;
      }
      setStatus("Push включён для этого браузера");
    } catch (err) {
      setStatus("Не удалось включить push");
      console.warn(err);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("hoocon-webpush-enable");
    if (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        void enablePush();
      });
    }
  });
})();
