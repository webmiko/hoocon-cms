/**
 * Admin: toggle Web Push for staff (заявки + чат поддержки).
 * Works with /admin/sw.js (Admin PWA scope) and falls back to legacy /sw.js.
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

  function getToggles() {
    return Array.prototype.slice.call(
      document.querySelectorAll(".hoocon-admin-push-toggle"),
    );
  }

  /**
   * @param {"off"|"on"|"pending"|"error"} state
   * @param {string} title
   */
  function setToggleState(state, title) {
    const on = state === "on";
    getToggles().forEach(function (btn) {
      btn.dataset.state = state;
      btn.setAttribute("aria-checked", on ? "true" : "false");
      btn.setAttribute("aria-busy", state === "pending" ? "true" : "false");
      btn.disabled = state === "pending";
      btn.title = title;
      btn.setAttribute(
        "aria-label",
        on
          ? "Push включён (заявки и чат) — нажмите, чтобы выключить"
          : "Push выключен — нажмите, чтобы включить заявки и чат",
      );
    });
  }

  /** Prefer Admin-scoped SW; keep legacy root SW if already subscribed. */
  async function ensureRegistration() {
    let adminReg = await navigator.serviceWorker.getRegistration("/admin/");
    if (adminReg) {
      const sub = await adminReg.pushManager.getSubscription();
      if (sub) return adminReg;
    }
    const rootReg = await navigator.serviceWorker.getRegistration("/");
    if (rootReg) {
      const sub = await rootReg.pushManager.getSubscription();
      if (sub) return rootReg;
    }
    const reg = await navigator.serviceWorker.register("/admin/sw.js", {
      scope: "/admin/",
    });
    await navigator.serviceWorker.ready;
    return reg;
  }

  async function refreshState() {
    if (!getToggles().length) return;
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setToggleState("error", "Браузер не поддерживает Web Push");
      getToggles().forEach(function (btn) {
        btn.disabled = true;
      });
      return;
    }
    try {
      const reg = await ensureRegistration();
      const sub = await reg.pushManager.getSubscription();
      const granted =
        typeof Notification !== "undefined" && Notification.permission === "granted";
      if (sub && granted) {
        setToggleState("on", "Push включён: заявки и чат");
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
      reg = await ensureRegistration();
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
      setToggleState("on", "Push включён: заявки и чат");
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
        await fetch("/api/webpush/topics/", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken"),
          },
          body: JSON.stringify({
            endpoint: json.endpoint,
            clear_support: true,
          }),
        });
      }
      setToggleState("off", "Push выключен");
    } catch (err) {
      setToggleState("error", "Не удалось выключить Push");
      console.warn(err);
    }
  }

  function bindToggles() {
    getToggles().forEach(function (btn) {
      if (btn.dataset.hooconPushBound === "1") return;
      btn.dataset.hooconPushBound = "1";
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
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindToggles();
    void refreshState();
    // Phone shell may clone from <template> after this script runs.
    window.setTimeout(function () {
      bindToggles();
      void refreshState();
    }, 400);
  });
})();
