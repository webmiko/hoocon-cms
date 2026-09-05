/**
 * Admin phone shell: activate ≤767px, more sheet, select-mode, tab active state.
 */
(function () {
  "use strict";

  var MQ = "(max-width: 767px)";
  var SELECT_STORAGE = "hoocon-phone-select-mode";

  function phoneMq() {
    return typeof window.matchMedia === "function"
      ? window.matchMedia(MQ)
      : { matches: false, addEventListener: function () {}, addListener: function () {} };
  }

  function shellEl() {
    return document.getElementById("hoocon-phone-shell");
  }

  function moreEl() {
    return document.getElementById("hoocon-phone-more");
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
  }

  function markActiveTab() {
    var path = window.location.pathname || "";
    var tabs = document.querySelectorAll("[data-hoocon-phone-tab]");
    tabs.forEach(function (tab) {
      var match = tab.getAttribute("data-match") || "";
      var isMore = tab.getAttribute("data-hoocon-phone-tab") === "more";
      var active = !isMore && match && path.indexOf(match) === 0;
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
    more.removeAttribute("hidden");
    if (btn) btn.setAttribute("aria-expanded", "true");
    document.body.classList.add("hoocon-phone-more-open");
  }

  function closeMore() {
    var more = moreEl();
    var btn = document.querySelector("[data-hoocon-phone-more-open]");
    if (!more) return;
    more.setAttribute("hidden", "");
    if (btn) btn.setAttribute("aria-expanded", "false");
    document.body.classList.remove("hoocon-phone-more-open");
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
    }
  }

  function onKey(event) {
    if (event.key === "Escape") {
      closeMore();
    }
  }

  function syncViewport() {
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
    if (!shellEl()) {
      return;
    }
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
