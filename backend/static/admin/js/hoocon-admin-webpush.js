/**
 * Admin: toggle support-chat Web Push for the logged-in staff user.
 * Compact switch in Unfold object-tools (header).
 */
(function () {
  "use strict";

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

  function getToggle() {
    return document.getElementById("hoocon-webpush-enable");
  }

  /**
   * @param {"off"|"on"|"pending"|"error"} state
   * @param {string} title
   */
  function setToggleState(state, title) {
    const btn = getToggle();
    if (!btn) return;
    const on = state === "on";
    btn.dataset.state = state;
    btn.setAttribute("aria-checked", on ? "true" : "false");
    btn.setAttribute("aria-busy", state === "pending" ? "true" : "false");
    btn.disabled = state === "pending";
    btn.title = title;
    btn.setAttribute(
      "aria-label",
      on ? "Push включён — нажмите, чтобы выключить" : "Push выключен — нажмите, чтобы включить",
    );
  }

  async function ensureRegistration() {
    let reg = await navigator.serviceWorker.getRegistration("/");
    if (!reg) {
      reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      await navigator.serviceWorker.ready;
    }
    return navigator.serviceWorker.ready;
  }

  async function refreshState() {
    const btn = getToggle();
    if (!btn) return;
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setToggleState("error", "Браузер не поддерживает Web Push");
      btn.disabled = true;
      return;
    }
    try {
      const reg = await ensureRegistration();
      const sub = await reg.pushManager.getSubscription();
      const granted =
        typeof Notification !== "undefined" && Notification.permission === "granted";
      if (sub && granted) {
        setToggleState("on", "Push включён");
      } else {
        setToggleState("off", "Push выключен");
      }
    } catch (_err) {
      setToggleState("off", "Push выключен");
    }
  }

  async function enablePush() {
    setToggleState("pending", "Подключаем Push…");
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setToggleState("error", "Браузер не поддерживает Web Push");
      return;
    }
    try {
      let reg = await ensureRegistration();
      const meta = await fetch("/api/webpush/vapid-public-key/").then((r) => r.json());
      if (!meta.configured || !meta.public_key) {
        setToggleState("error", "VAPID не настроен на сервере");
        return;
      }
      const perm = await Notification.requestPermission();
      if (perm !== "granted") {
        setToggleState("error", "Нужно разрешение уведомлений");
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
        setToggleState("error", "Ошибка подписки (" + resp.status + ")");
        return;
      }
      setToggleState("on", "Push включён");
    } catch (err) {
      setToggleState("error", "Не удалось включить Push");
      console.warn(err);
    }
  }

  async function disablePush() {
    setToggleState("pending", "Отключаем Push…");
    try {
      const reg = await ensureRegistration();
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        const json = sub.toJSON();
        await fetch("/api/webpush/unsubscribe/", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken"),
          },
          body: JSON.stringify({ endpoint: json.endpoint }),
        });
        await sub.unsubscribe();
      }
      setToggleState("off", "Push выключен");
    } catch (err) {
      setToggleState("error", "Не удалось выключить Push");
      console.warn(err);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const btn = getToggle();
    if (!btn) return;
    void refreshState();
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      if (btn.disabled) return;
      const on = btn.getAttribute("aria-checked") === "true";
      if (on) {
        void disablePush();
      } else {
        void enablePush();
      }
    });
  });
})();
