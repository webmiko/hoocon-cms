/**
 * iOS 27 Settings-style Admin phone hub: account card + grouped drill-down.
 */
(function () {
  "use strict";

  var MQ = "(max-width: 767px)";
  var DASHBOARD_QUERY = "hoocon_view=dashboard";

  function phoneMq() {
    return typeof window.matchMedia === "function"
      ? window.matchMedia(MQ)
      : { matches: false, addEventListener: function () {}, addListener: function () {} };
  }

  function settingsRoot() {
    return document.querySelector("[data-hoocon-phone-settings]");
  }

  function isAdminIndexPath() {
    var path = window.location.pathname || "";
    return path === "/admin" || path === "/admin/";
  }

  function isDashboardView() {
    try {
      return new URL(window.location.href).searchParams.get("hoocon_view") === "dashboard";
    } catch (_err) {
      return false;
    }
  }

  function setHubMode(on) {
    document.body.classList.toggle("hoocon-phone-settings-hub", on);
  }

  function setDetailMode(on) {
    document.body.classList.toggle("hoocon-phone-settings-detail", on);
  }

  function setAccountMode(on) {
    document.body.classList.toggle("hoocon-phone-settings-account", on);
  }

  function setDashboardMode(on) {
    document.body.classList.toggle("hoocon-phone-settings-dashboard", on);
  }

  function headerTitleEl() {
    return document.querySelector(".hoocon-admin-header h1");
  }

  var savedHeaderTitle = "";

  function updateHeaderBack(title, showBack) {
    var back = document.querySelector("[data-hoocon-settings-header-back]");
    var heading = headerTitleEl();
    if (showBack) {
      if (back) {
        back.removeAttribute("hidden");
        var label = back.querySelector("[data-hoocon-settings-header-back-label]");
        if (label) {
          label.textContent = title || "Настройки";
        }
      }
      if (heading && title) {
        if (!savedHeaderTitle) {
          savedHeaderTitle = heading.textContent || "";
        }
        heading.textContent = title;
      }
    } else {
      if (back) {
        back.setAttribute("hidden", "");
      }
      if (heading && savedHeaderTitle) {
        heading.textContent = savedHeaderTitle;
        savedHeaderTitle = "";
      }
    }
  }

  function openAccountPage() {
    var rootPane = document.querySelector("[data-hoocon-settings-root]");
    var detailPane = document.querySelector("[data-hoocon-settings-detail]");
    var accountPane = document.querySelector("[data-hoocon-settings-account-detail]");
    var btn = document.querySelector("[data-hoocon-settings-account-open]");
    if (!rootPane || !accountPane) {
      return;
    }
    if (detailPane) {
      detailPane.setAttribute("hidden", "");
    }
    rootPane.setAttribute("hidden", "");
    accountPane.removeAttribute("hidden");
    setDetailMode(false);
    setAccountMode(true);
    setHubMode(true);
    if (btn) {
      btn.setAttribute("aria-expanded", "true");
    }
    var title =
      (btn && btn.getAttribute("data-hoocon-settings-account-title")) || "Учётная запись";
    updateHeaderBack(title, true);
    if (window.history && typeof window.history.pushState === "function") {
      window.history.pushState({ hooconSettingsAccount: true }, "", window.location.href);
    }
  }

  function closeAccountPage() {
    var rootPane = document.querySelector("[data-hoocon-settings-root]");
    var accountPane = document.querySelector("[data-hoocon-settings-account-detail]");
    var btn = document.querySelector("[data-hoocon-settings-account-open]");
    if (!rootPane || !accountPane) {
      return;
    }
    accountPane.setAttribute("hidden", "");
    rootPane.removeAttribute("hidden");
    setAccountMode(false);
    if (btn) {
      btn.setAttribute("aria-expanded", "false");
    }
    updateHeaderBack("", false);
  }

  function openGroup(groupId, groupTitle) {
    var rootPane = document.querySelector("[data-hoocon-settings-root]");
    var detailPane = document.querySelector("[data-hoocon-settings-detail]");
    var accountPane = document.querySelector("[data-hoocon-settings-account-detail]");
    var list = document.querySelector("[data-hoocon-settings-detail-list]");
    var tpl = document.getElementById("hoocon-settings-group-" + groupId);
    if (!rootPane || !detailPane || !list || !tpl) {
      return;
    }

    if (accountPane) {
      accountPane.setAttribute("hidden", "");
    }
    setAccountMode(false);
    list.innerHTML = "";
    list.appendChild(tpl.content.cloneNode(true));
    rootPane.setAttribute("hidden", "");
    detailPane.removeAttribute("hidden");
    setDetailMode(true);
    updateHeaderBack(groupTitle || "Настройки", true);

    if (window.history && typeof window.history.pushState === "function") {
      window.history.pushState({ hooconSettingsGroup: groupId }, "", window.location.href);
    }
  }

  function resetDetailUI() {
    var rootPane = document.querySelector("[data-hoocon-settings-root]");
    var detailPane = document.querySelector("[data-hoocon-settings-detail]");
    var accountPane = document.querySelector("[data-hoocon-settings-account-detail]");
    if (!rootPane || !detailPane) {
      return;
    }
    detailPane.setAttribute("hidden", "");
    if (accountPane) {
      accountPane.setAttribute("hidden", "");
    }
    rootPane.removeAttribute("hidden");
    setDetailMode(false);
    setAccountMode(false);
    updateHeaderBack("", false);
    var btn = document.querySelector("[data-hoocon-settings-account-open]");
    if (btn) {
      btn.setAttribute("aria-expanded", "false");
    }
  }

  function closeGroup() {
    resetDetailUI();
  }

  function showSettingsHub() {
    var hub = settingsRoot();
    if (!hub) {
      return;
    }
    hub.removeAttribute("hidden");
    setHubMode(true);
    setDashboardMode(false);
    resetDetailUI();
    updateHeaderBack("", false);
  }

  function hideSettingsHub() {
    var hub = settingsRoot();
    if (!hub) {
      return;
    }
    hub.setAttribute("hidden", "");
    setHubMode(false);
    setDetailMode(false);
    setAccountMode(false);
    setDashboardMode(false);
    updateHeaderBack("", false);
  }

  function syncView() {
    if (!phoneMq().matches || !isAdminIndexPath()) {
      hideSettingsHub();
      return;
    }

    var hub = settingsRoot();
    if (!hub) {
      hideSettingsHub();
      return;
    }

    if (isDashboardView()) {
      hub.setAttribute("hidden", "");
      setHubMode(false);
      setDetailMode(false);
      setAccountMode(false);
      setDashboardMode(true);
      updateHeaderBack("Настройки", true);
      return;
    }

    hub.removeAttribute("hidden");
    setDashboardMode(false);
    setHubMode(true);
    resetDetailUI();
  }

  function onDocClick(event) {
    var target = event.target;
    if (!(target instanceof Element)) {
      return;
    }

    if (target.closest("[data-hoocon-settings-account-open]")) {
      if (!phoneMq().matches) {
        return;
      }
      event.preventDefault();
      openAccountPage();
      return;
    }
    if (target.closest("[data-hoocon-settings-dashboard]")) {
      /* Dashboard row navigates to full summary screen (iOS detail push). */
      return;
    }
    if (target.closest("[data-hoocon-settings-open]")) {
      event.preventDefault();
      var btn = target.closest("[data-hoocon-settings-open]");
      if (!btn) {
        return;
      }
      openGroup(
        btn.getAttribute("data-hoocon-settings-open") || "",
        btn.getAttribute("data-hoocon-settings-title") || "",
      );
      return;
    }
    if (target.closest("[data-hoocon-settings-header-back]")) {
      event.preventDefault();
      if (isDashboardView()) {
        window.location.href = "/admin/";
        return;
      }
      if (document.body.classList.contains("hoocon-phone-settings-account")) {
        closeAccountPage();
        return;
      }
      if (document.body.classList.contains("hoocon-phone-settings-detail")) {
        closeGroup();
      }
    }
  }

  function onKey(event) {
    if (event.key !== "Escape" || !phoneMq().matches) {
      return;
    }
    if (document.body.classList.contains("hoocon-phone-settings-account")) {
      closeAccountPage();
      return;
    }
    if (document.body.classList.contains("hoocon-phone-settings-detail")) {
      closeGroup();
    }
  }

  function onPopState() {
    if (!phoneMq().matches || !isAdminIndexPath() || isDashboardView()) {
      return;
    }
    if (document.body.classList.contains("hoocon-phone-settings-account")) {
      closeAccountPage();
      return;
    }
    if (document.body.classList.contains("hoocon-phone-settings-detail")) {
      closeGroup();
    }
  }

  function init() {
    syncView();
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKey);
    var mq = phoneMq();
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", syncView);
    } else if (typeof mq.addListener === "function") {
      mq.addListener(syncView);
    }
    window.addEventListener("resize", syncView);
    window.addEventListener("popstate", onPopState);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
