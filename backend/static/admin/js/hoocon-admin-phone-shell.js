/**
 * Admin phone shell: activate ≤767px, more sheet, select-mode, tab active state,
 * page actions (Unfold action_list + object-tools) into the bottom «Ещё» sheet.
 */
(function () {
  "use strict";

  var MQ = "(max-width: 767px)";
  var SELECT_STORAGE = "hoocon-phone-select-mode";
  /* Cursor Simple Browser paints over bottom:0; lift tabs above that chrome. */
  var CURSOR_VIEWPORT_INSET = "3.25rem";

  function phoneMq() {
    return typeof window.matchMedia === "function"
      ? window.matchMedia(MQ)
      : { matches: false, addEventListener: function () {}, addListener: function () {} };
  }

  function isCursorEmbeddedBrowser() {
    return /Cursor\//i.test(navigator.userAgent || "");
  }

  function syncViewportInset() {
    var root = document.documentElement;
    if (!root || !root.style) return;
    if (isCursorEmbeddedBrowser() && phoneMq().matches) {
      root.style.setProperty("--hoocon-phone-viewport-inset", CURSOR_VIEWPORT_INSET);
    } else {
      root.style.removeProperty("--hoocon-phone-viewport-inset");
    }
  }

  function ensureShellMounted() {
    var shell = document.getElementById("hoocon-phone-shell");
    var freshlyCloned = false;
    if (!shell) {
      var tpl = document.getElementById("hoocon-phone-shell-template");
      if (!tpl || !tpl.content) {
        return false;
      }
      document.body.appendChild(tpl.content.cloneNode(true));
      shell = document.getElementById("hoocon-phone-shell");
      freshlyCloned = true;
    }
    // Footer render lives under #main; reparent so position:fixed sticks to the
    // viewport (Unfold long pages / embedded browsers otherwise bury the bar).
    if (shell && shell.parentElement !== document.body) {
      document.body.appendChild(shell);
    }
    if (
      freshlyCloned &&
      shell &&
      window.Alpine &&
      typeof window.Alpine.initTree === "function"
    ) {
      try {
        window.Alpine.initTree(shell);
      } catch (_err) {
        /* theme switch still usable from sidebar on desktop */
      }
    }
    return Boolean(shell);
  }

  function shellEl() {
    ensureShellMounted();
    return document.getElementById("hoocon-phone-shell");
  }

  function moreEl() {
    return document.getElementById("hoocon-phone-more");
  }

  function headerMenuRoot() {
    return document.querySelector("[data-hoocon-phone-header-menu]");
  }

  function headerMenuList() {
    return document.querySelector("[data-hoocon-phone-header-menu-list]");
  }

  function headerToolsSource() {
    return document.querySelector("[data-hoocon-header-object-tools]");
  }

  function isAddTool(node) {
    if (!(node instanceof Element)) return false;
    if (node.matches("a.addlink")) return true;
    if (node.querySelector("a.addlink")) return true;
    return false;
  }

  function isDesktopOnlyTool(node) {
    if (!(node instanceof Element)) return false;
    // Стена/Канбан toggle is desktop-only (kanban layout starts at 768px).
    return node.classList.contains("hoocon-lead-view-tool");
  }

  function closeHeaderMenu() {
    var root = headerMenuRoot();
    var panel = document.querySelector("[data-hoocon-phone-header-menu-panel]");
    var btn = document.querySelector("[data-hoocon-phone-header-menu-open]");
    if (panel) panel.setAttribute("hidden", "");
    if (btn) btn.setAttribute("aria-expanded", "false");
    if (root) root.classList.remove("is-open");
  }

  function openHeaderMenu() {
    var root = headerMenuRoot();
    var panel = document.querySelector("[data-hoocon-phone-header-menu-panel]");
    var btn = document.querySelector("[data-hoocon-phone-header-menu-open]");
    if (!panel || !btn) return;
    panel.removeAttribute("hidden");
    btn.setAttribute("aria-expanded", "true");
    if (root) root.classList.add("is-open");
  }

  function toggleHeaderMenu() {
    var panel = document.querySelector("[data-hoocon-phone-header-menu-panel]");
    if (!panel) return;
    if (panel.hasAttribute("hidden")) {
      openHeaderMenu();
    } else {
      closeHeaderMenu();
    }
  }

  function actionListRoot() {
    return document.querySelector("[data-hoocon-phone-action-list]");
  }

  function actionListUl() {
    var root = actionListRoot();
    return root ? root.querySelector("ul.bg-white") : null;
  }

  function pageActionsMount() {
    return document.querySelector("[data-hoocon-phone-more-page-actions]");
  }

  function pageActionsWrap() {
    return document.querySelector("[data-hoocon-phone-more-page-actions-wrap]");
  }

  var PAGE_ACTION_FROM = "data-hoocon-phone-page-action-from";

  function syncPageActionsVisibility() {
    var mount = pageActionsMount();
    var wrap = pageActionsWrap();
    if (!mount || !wrap) return;
    if (mount.children.length) {
      wrap.removeAttribute("hidden");
    } else {
      wrap.setAttribute("hidden", "");
    }
  }

  function movePageAction(node, from, mount) {
    node.setAttribute(PAGE_ACTION_FROM, from);
    mount.appendChild(node);
  }

  function restorePageActionsFrom(from, target) {
    var mount = pageActionsMount();
    if (!mount || !target) return;
    Array.prototype.slice.call(mount.children).forEach(function (child) {
      if (child.getAttribute(PAGE_ACTION_FROM) !== from) return;
      child.removeAttribute(PAGE_ACTION_FROM);
      target.appendChild(child);
    });
  }

  function hideHeaderMenuShell() {
    var root = headerMenuRoot();
    if (!root) return;
    root.setAttribute("hidden", "");
    closeHeaderMenu();
  }

  function relocateActionList(toPhone) {
    var ul = actionListUl();
    var mount = pageActionsMount();
    if (!ul || !mount) return;

    if (toPhone) {
      while (ul.firstElementChild) {
        movePageAction(ul.firstElementChild, "action-list", mount);
      }
    } else {
      restorePageActionsFrom("action-list", ul);
    }
    syncPageActionsVisibility();
  }

  function relocateHeaderTools(toPhone) {
    var source = headerToolsSource();
    var mount = pageActionsMount();
    if (!source || !mount) return;

    if (toPhone) {
      Array.prototype.slice.call(source.children).forEach(function (child) {
        if (isAddTool(child)) return;
        if (isDesktopOnlyTool(child)) {
          child.setAttribute("hidden", "");
          return;
        }
        movePageAction(child, "header-tools", mount);
      });
      hideHeaderMenuShell();
    } else {
      restorePageActionsFrom("header-tools", source);
      Array.prototype.slice.call(source.querySelectorAll(".hoocon-lead-view-tool[hidden]")).forEach(
        function (child) {
          child.removeAttribute("hidden");
        },
      );
      hideHeaderMenuShell();
    }
    syncPageActionsVisibility();
  }

  function setReady(on) {
    document.body.classList.toggle("hoocon-phone-ready", on);
    var shell = shellEl();
    if (shell) {
      if (on) {
        shell.removeAttribute("hidden");
      } else {
        shell.setAttribute("hidden", "");
        closeMore();
      }
    }
    relocateHeaderTools(on);
    relocateActionList(on);
  }

  function normalizeAdminPath(path) {
    var p = path || "";
    if (p.length > 1 && p.charAt(p.length - 1) === "/") {
      p = p.slice(0, -1);
    }
    return p || "/";
  }

  function markActiveTab() {
    var path = window.location.pathname || "";
    var pathNorm = normalizeAdminPath(path);
    var tabs = document.querySelectorAll("[data-hoocon-phone-tab]");
    tabs.forEach(function (tab) {
      var match = tab.getAttribute("data-match") || "";
      var isMore = tab.getAttribute("data-hoocon-phone-tab") === "more";
      var exact = tab.hasAttribute("data-match-exact");
      var active = false;
      if (isMore) {
        active = document.body.classList.contains("hoocon-phone-more-open");
      } else if (match) {
        if (exact) {
          active = pathNorm === normalizeAdminPath(match);
        } else {
          active = path.indexOf(match) === 0;
        }
      }
      tab.classList.toggle("hoocon-phone-tab--active", Boolean(active));
      if (tab.tagName === "A") {
        if (active) {
          tab.setAttribute("aria-current", "page");
        } else {
          tab.removeAttribute("aria-current");
        }
      }
    });
  }

  function openMore() {
    var more = moreEl();
    var btn = document.querySelector("[data-hoocon-phone-more-open]");
    if (!more) return;
    closeHeaderMenu();
    more.removeAttribute("hidden");
    if (btn) btn.setAttribute("aria-expanded", "true");
    document.body.classList.add("hoocon-phone-more-open");
    markActiveTab();
  }

  function closeMore() {
    var more = moreEl();
    var btn = document.querySelector("[data-hoocon-phone-more-open]");
    if (!more) return;
    more.setAttribute("hidden", "");
    if (btn) btn.setAttribute("aria-expanded", "false");
    document.body.classList.remove("hoocon-phone-more-open");
    markActiveTab();
  }

  function toggleMore() {
    var more = moreEl();
    if (!more) return;
    if (more.hasAttribute("hidden")) {
      openMore();
    } else {
      closeMore();
    }
  }

  function ensureSelectToggle() {
    var form = document.getElementById("changelist-form");
    if (!form || document.querySelector(".hoocon-phone-select-toggle")) {
      return;
    }
    var hasCheckbox = form.querySelector(".action-select, .action-checkbox");
    if (!hasCheckbox) {
      return;
    }
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "hoocon-phone-select-toggle";
    btn.setAttribute("data-hoocon-phone-select-toggle", "");
    btn.textContent = document.body.classList.contains("hoocon-phone-select-mode")
      ? "Готово"
      : "Выбрать";
    var toolbar =
      form.querySelector(".actions") ||
      document.getElementById("toolbar") ||
      form;
    if (toolbar && toolbar !== form) {
      toolbar.parentNode.insertBefore(btn, toolbar);
    } else {
      form.insertBefore(btn, form.firstChild);
    }
  }

  function setSelectMode(on) {
    document.body.classList.toggle("hoocon-phone-select-mode", on);
    try {
      window.sessionStorage.setItem(SELECT_STORAGE, on ? "1" : "0");
    } catch (_err) {
      /* ignore */
    }
    var btn = document.querySelector("[data-hoocon-phone-select-toggle]");
    if (btn) {
      btn.textContent = on ? "Готово" : "Выбрать";
    }
  }

  function restoreSelectMode() {
    var saved = "0";
    try {
      saved = window.sessionStorage.getItem(SELECT_STORAGE) || "0";
    } catch (_err) {
      saved = "0";
    }
    setSelectMode(saved === "1");
  }

  function onDocClick(event) {
    var target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest("[data-hoocon-phone-header-menu-open]")) {
      event.preventDefault();
      closeMore();
      toggleHeaderMenu();
      return;
    }
    if (target.closest("[data-hoocon-phone-more-open]")) {
      event.preventDefault();
      toggleMore();
      return;
    }
    if (target.closest("[data-hoocon-phone-more-close]")) {
      event.preventDefault();
      closeMore();
      return;
    }
    if (target.closest("[data-hoocon-phone-select-toggle]")) {
      event.preventDefault();
      setSelectMode(!document.body.classList.contains("hoocon-phone-select-mode"));
      return;
    }
    if (
      document.querySelector(".hoocon-phone-header-menu.is-open") &&
      !target.closest("[data-hoocon-phone-header-menu]")
    ) {
      closeHeaderMenu();
    }
  }

  function onKey(event) {
    if (event.key === "Escape") {
      closeMore();
      closeHeaderMenu();
    }
  }

  function syncViewport() {
    syncViewportInset();
    setReady(phoneMq().matches);
    if (phoneMq().matches) {
      markActiveTab();
      ensureSelectToggle();
      restoreSelectMode();
    } else {
      document.body.classList.remove("hoocon-phone-select-mode");
    }
  }

  function init() {
    ensureShellMounted();
    syncViewport();
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKey);
    var mq = phoneMq();
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", syncViewport);
    } else if (typeof mq.addListener === "function") {
      mq.addListener(syncViewport);
    }
    window.addEventListener("resize", syncViewport);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
