/**
 * Live Admin badges: leads sticker + sidebar support/leads counts without F5.
 * Also re-binds staff Web Push subscription when Notification.permission is granted.
 *
 * Data attributes (optional, on <body> or #container via base_site):
 *   data-hoocon-leads-count-url
 *   data-hoocon-support-unread-url
 */
(function () {
  "use strict";

  var POLL_MS = 12000;

  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function leadsCountUrl() {
    var el = document.querySelector("[data-hoocon-leads-count-url]");
    if (el) return el.getAttribute("data-hoocon-leads-count-url") || "";
    var script = document.querySelector(
      "script[data-count-url][src*='hoocon-admin-leads-sticker']",
    );
    return (script && script.getAttribute("data-count-url")) || "";
  }

  function supportUnreadUrl() {
    var el = document.querySelector("[data-hoocon-support-unread-url]");
    return (el && el.getAttribute("data-hoocon-support-unread-url")) || "";
  }

  /**
   * Update or insert a sidebar .sidebar-badge next to a nav link.
   * @param {string} hrefPart
   * @param {number} count
   */
  function setSidebarBadge(hrefPart, count) {
    var links = document.querySelectorAll("#nav-sidebar-apps a[href]");
    var target = null;
    for (var i = 0; i < links.length; i += 1) {
      var href = links[i].getAttribute("href") || "";
      if (href.indexOf(hrefPart) >= 0) {
        target = links[i];
        break;
      }
    }
    if (!target) return;
    var badge = target.querySelector(".sidebar-badge");
    var safe = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
    if (safe <= 0) {
      if (badge) badge.remove();
      return;
    }
    if (!badge) {
      badge = document.createElement("span");
      badge.className =
        "sidebar-badge font-semibold h-[18px] leading-[18px] ml-2 px-1 relative " +
        "rounded-xs text-center text-[11px] whitespace-nowrap uppercase min-w-[18px] " +
        "text-white text-shadow-xs bg-red-500";
      target.appendChild(badge);
    }
    badge.textContent = String(safe);
  }

  function setPhoneBadge(selector, count) {
    var el = document.querySelector(selector);
    if (!el) return;
    var safe = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
    if (safe <= 0) {
      el.hidden = true;
      el.textContent = "0";
      return;
    }
    el.hidden = false;
    el.textContent = safe > 99 ? "99+" : String(safe);
  }

  function applyLeads(count) {
    var safe = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
    var sticker = document.getElementById("hoocon-admin-lead-sticker");
    var countEl = document.querySelector("[data-hoocon-new-leads-count]");
    if (countEl) countEl.textContent = String(safe);
    if (sticker) {
      sticker.classList.toggle("hoocon-admin-lead-sticker--active", safe > 0);
      sticker.setAttribute("aria-label", "Новые непросмотренные заявки: " + safe);
      sticker.hidden = safe === 0;
    }
    setSidebarBadge("/admin/leads/lead/", safe);
    setPhoneBadge("[data-hoocon-phone-leads-badge]", safe);
  }

  function applySupport(count) {
    var safe = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
    setSidebarBadge("/admin/supportchat/conversation/", safe);
    var sticker = document.getElementById("hoocon-admin-support-sticker");
    var countEl = document.querySelector("[data-hoocon-support-unread-count]");
    if (countEl) countEl.textContent = String(safe);
    if (sticker) {
      sticker.classList.toggle("hoocon-admin-lead-sticker--active", safe > 0);
      sticker.classList.toggle("hoocon-admin-support-sticker--active", safe > 0);
      sticker.setAttribute("aria-label", "Новые сообщения поддержки: " + safe);
      sticker.hidden = safe === 0;
    }
    setPhoneBadge("[data-hoocon-phone-support-badge]", safe);
    document.dispatchEvent(
      new CustomEvent("hoocon:support-unread", { detail: { count: safe } }),
    );
  }

  async function fetchJson(url) {
    if (!url) return null;
    var resp = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!resp.ok) return null;
    return resp.json();
  }

  async function refresh() {
    if (document.hidden) return;
    try {
      var leadsUrl = leadsCountUrl();
      if (leadsUrl) {
        var leads = await fetchJson(leadsUrl);
        if (leads && typeof leads.count !== "undefined") {
          applyLeads(Number(leads.count) || 0);
        }
      }
      var supportUrl = supportUnreadUrl();
      if (supportUrl) {
        var support = await fetchJson(supportUrl);
        if (support && typeof support.count !== "undefined") {
          applySupport(Number(support.count) || 0);
        }
      }
    } catch (_err) {
      /* next poll retries */
    }
  }

  function urlBase64ToUint8Array(base64String) {
    var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    var raw = window.atob(base64);
    var output = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
    return output;
  }

  /** Re-POST existing push subscription so staff alerts work after reload. */
  async function syncStaffPush() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    if (typeof Notification === "undefined" || Notification.permission !== "granted") {
      return;
    }
    try {
      var reg = await navigator.serviceWorker.getRegistration("/");
      if (!reg) {
        reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
        await navigator.serviceWorker.ready;
      }
      reg = await navigator.serviceWorker.ready;
      var sub = await reg.pushManager.getSubscription();
      if (!sub) return;
      var json = sub.toJSON();
      if (!json.endpoint || !json.keys) return;
      await fetch("/api/webpush/subscribe/", {
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
    } catch (_err) {
      /* ignore — enable button on support list still works */
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    void refresh();
    void syncStaffPush();
    window.setInterval(function () {
      void refresh();
    }, POLL_MS);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) void refresh();
    });
  });
})();
