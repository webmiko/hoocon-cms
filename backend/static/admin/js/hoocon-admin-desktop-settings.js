/**
 * macOS 27 System Settings-style Admin desktop: sidebar highlight + index drill-down.
 * Sidebar rows are real links — no click interception (avoids dead buttons on /admin/).
 */
(function () {
  "use strict";

  /* Match OS27 settings sidebar (tablet flyout + desktop panel from 768px). */
  var DESKTOP_MQ = "(min-width: 768px)";
  var APP_QUERY = "hoocon_app";
  var VIEW_QUERY = "hoocon_view";
  var ACCOUNT_VIEW = "account";

  function desktopMq() {
    return typeof window.matchMedia === "function"
      ? window.matchMedia(DESKTOP_MQ)
      : { matches: false, addEventListener: function () {}, addListener: function () {} };
  }

  function isAdminIndexPath() {
    var path = window.location.pathname || "";
    return path === "/admin" || path === "/admin/";
  }

  function currentParams() {
    try {
      return new URL(window.location.href).searchParams;
    } catch (_err) {
      return new URLSearchParams();
    }
  }

  function detailRoot() {
    return document.querySelector("[data-hoocon-desktop-settings-detail]");
  }

  function accountRoot() {
    return document.querySelector("[data-hoocon-desktop-settings-account]");
  }

  function modelsList() {
    return document.querySelector("[data-hoocon-desktop-settings-models]");
  }

  function heroIcon() {
    return document.querySelector("[data-hoocon-desktop-settings-hero-icon]");
  }

  function heroSymbol() {
    return document.querySelector("[data-hoocon-desktop-settings-hero-symbol]");
  }

  function heroTitle() {
    return document.querySelector("[data-hoocon-desktop-settings-hero-title]");
  }

  function heroDesc() {
    return document.querySelector("[data-hoocon-desktop-settings-hero-desc]");
  }

  function setIndexMode(mode) {
    document.body.classList.remove(
      "hoocon-desktop-settings-index",
      "hoocon-desktop-settings-dashboard",
      "hoocon-desktop-settings-app",
      "hoocon-desktop-settings-account",
    );
    if (mode) {
      document.body.classList.add(mode);
    }
  }

  function activeNavIdFromPath() {
    var path = window.location.pathname || "";
    if (path.indexOf("/admin/supportchat/conversation") === 0) {
      return "supportchat-messages";
    }
    if (path.indexOf("/admin/supportchat/") === 0) {
      return "supportchat";
    }
    var match = path.match(/^\/admin\/([^/]+)\//);
    return match ? match[1] : "";
  }

  function highlightSidebar(navId) {
    var rows = document.querySelectorAll("[data-hoocon-desktop-settings-select]");
    rows.forEach(function (row) {
      var id = row.getAttribute("data-hoocon-desktop-settings-select") || "";
      row.classList.toggle("is-active", Boolean(navId && id === navId));
    });
  }

  function readRowMeta(row) {
    return {
      id: row.getAttribute("data-hoocon-desktop-settings-select") || "",
      title: row.getAttribute("data-hoocon-desktop-settings-title") || "",
      icon: row.getAttribute("data-hoocon-desktop-settings-icon") || "folder",
      iconBg: row.getAttribute("data-hoocon-desktop-settings-icon-bg") || "",
      iconFg: row.getAttribute("data-hoocon-desktop-settings-icon-fg") || "",
      description: row.getAttribute("data-hoocon-desktop-settings-description") || "",
    };
  }

  function updateHero(meta) {
    if (heroSymbol()) {
      heroSymbol().textContent = meta.icon || "folder";
    }
    if (heroIcon() && meta.iconBg) {
      heroIcon().style.setProperty("--settings-icon-bg", meta.iconBg);
      heroIcon().style.setProperty("--settings-icon-fg", meta.iconFg || "#ffffff");
    }
    if (heroTitle()) {
      heroTitle().textContent = meta.title || "Раздел";
    }
    if (heroDesc()) {
      if (meta.description) {
        heroDesc().textContent = meta.description;
        heroDesc().removeAttribute("hidden");
      } else {
        heroDesc().textContent = "";
        heroDesc().setAttribute("hidden", "");
      }
    }
  }

  function hideSplitViews() {
    var detail = detailRoot();
    var account = accountRoot();
    if (detail) {
      detail.setAttribute("hidden", "");
    }
    if (account) {
      account.setAttribute("hidden", "");
    }
  }

  function appTemplate(appId) {
    return document.getElementById("hoocon-settings-group-" + appId);
  }

  function navigateToFirstAppModel(appId) {
    var tpl = appTemplate(appId);
    if (!tpl || !tpl.content) {
      return false;
    }
    var link = tpl.content.querySelector("a.hoocon-phone-settings__row--link");
    if (!link || !link.href) {
      return false;
    }
    window.location.replace(link.href);
    return true;
  }

  function openAppDetail(appId) {
    var detail = detailRoot();
    var list = modelsList();
    var tpl = appTemplate(appId);
    var row = document.querySelector(
      '[data-hoocon-desktop-settings-select="' + appId + '"]',
    );
    if (!detail || !list || !tpl || !row) {
      return false;
    }

    hideSplitViews();
    list.innerHTML = "";
    list.appendChild(tpl.content.cloneNode(true));
    updateHero(readRowMeta(row));
    detail.removeAttribute("hidden");
    setIndexMode("hoocon-desktop-settings-app");
    highlightSidebar(appId);
    return true;
  }

  function showAccountPage() {
    var account = accountRoot();
    if (!account) {
      return false;
    }
    hideSplitViews();
    account.removeAttribute("hidden");
    setIndexMode("hoocon-desktop-settings-account");
    highlightSidebar("account");
    return true;
  }

  function showDashboard() {
    hideSplitViews();
    setIndexMode("hoocon-desktop-settings-dashboard");
    highlightSidebar("home");
  }

  function hideDesktopIndexUi() {
    hideSplitViews();
    setIndexMode("");
  }

  function syncIndexView() {
    if (!desktopMq().matches || !isAdminIndexPath()) {
      hideDesktopIndexUi();
      return;
    }

    document.body.classList.add("hoocon-desktop-settings-index");
    var params = currentParams();
    var appId = params.get(APP_QUERY) || "";
    var view = params.get(VIEW_QUERY) || "";

    if (view === ACCOUNT_VIEW) {
      if (showAccountPage()) {
        return;
      }
    }

    if (view === "dashboard") {
      showDashboard();
      return;
    }

    if (!appId && !view) {
      showDashboard();
      return;
    }

    if (appId && openAppDetail(appId)) {
      return;
    }

    if (appId && navigateToFirstAppModel(appId)) {
      return;
    }

    showDashboard();
  }

  function syncSidebarActive() {
    if (!desktopMq().matches) {
      highlightSidebar("");
      return;
    }
    if (isAdminIndexPath()) {
      var params = currentParams();
      var appId = params.get(APP_QUERY) || "";
      var view = params.get(VIEW_QUERY) || "";
      if (view === ACCOUNT_VIEW) {
        highlightSidebar("account");
        return;
      }
      if (view === "dashboard" || (!appId && !view)) {
        highlightSidebar("home");
      } else if (appId) {
        highlightSidebar(appId);
      }
      return;
    }
    highlightSidebar(activeNavIdFromPath());
  }

  function init() {
    syncIndexView();
    syncSidebarActive();
    var mq = desktopMq();
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", function () {
        syncIndexView();
        syncSidebarActive();
      });
    } else if (typeof mq.addListener === "function") {
      mq.addListener(function () {
        syncIndexView();
        syncSidebarActive();
      });
    }
    window.addEventListener("resize", syncSidebarActive);
    window.addEventListener("popstate", syncIndexView);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
