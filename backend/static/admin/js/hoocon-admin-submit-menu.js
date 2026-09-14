/**
 * Change-form submit row: collapse save actions into a «Сохранить ▾» menu when
 * the bar is too narrow (phone/tablet or desktop with sidebar).
 */
(function () {
  "use strict";

  var TABLET_MQ = "(max-width: 1023px)";
  var SAVE_NAMES = ["_save", "_continue", "_addanother", "_saveasnew"];
  var MENU_CLASS = "hoocon-submit-menu";
  var ACTIVE_CLASS = "hoocon-submit-menu-active";
  var ROW_HEIGHT_PX = 72;
  var PANEL_GAP_PX = 6;
  var VIEWPORT_INSET_PX = 8;

  /** @type {{ container: HTMLElement | null, menu: HTMLElement | null, open: boolean, observer: ResizeObserver | null, mutator: MutationObserver | null }} */
  var state = {
    container: null,
    menu: null,
    open: false,
    observer: null,
    mutator: null,
  };

  function tabletMq() {
    return typeof window.matchMedia === "function"
      ? window.matchMedia(TABLET_MQ)
      : { matches: false, addEventListener: function () {}, addListener: function () {} };
  }

  function isChangeForm() {
    return document.body.classList.contains("change-form");
  }

  function getContainer() {
    var row = document.getElementById("submit-row");
    if (!row) {
      return null;
    }
    return row.querySelector(".container");
  }

  function getSaveButtons(container) {
    return SAVE_NAMES.map(function (name) {
      return container.querySelector('button[name="' + name + '"]');
    }).filter(Boolean);
  }

  /** Reuse Unfold submit-button classes on the menu trigger (primary «Сохранить»). */
  function unfoldTriggerClasses(sourceButton) {
    return (sourceButton.className || "")
      .split(/\s+/)
      .filter(function (token) {
        return token && token !== "hoocon-submit-menu__action";
      })
      .join(" ");
  }

  function visibleBarChildren(container) {
    return Array.from(container.children).filter(function (el) {
      return !el.classList.contains(MENU_CLASS);
    });
  }

  function rowNeedsCollapse(container, buttons) {
    if (buttons.length < 2) {
      return false;
    }
    if (tabletMq().matches) {
      return true;
    }

    var row = document.getElementById("submit-row");
    if (row && row.offsetHeight > ROW_HEIGHT_PX) {
      return true;
    }
    if (container.scrollHeight > ROW_HEIGHT_PX) {
      return true;
    }

    var total = 0;
    var gap = 10;
    visibleBarChildren(container).forEach(function (el, index) {
      total += el.offsetWidth;
      if (index > 0) {
        total += gap;
      }
    });
    return total > container.clientWidth + 2;
  }

  function resetPanelPosition(panel) {
    if (!panel) {
      return;
    }
    panel.style.position = "";
    panel.style.left = "";
    panel.style.right = "";
    panel.style.top = "";
    panel.style.bottom = "";
    panel.style.width = "";
  }

  function positionOpenPanel() {
    if (!state.menu || !state.open) {
      return;
    }
    var panel = state.menu.querySelector(".hoocon-submit-menu__panel");
    var trigger = state.menu.querySelector(".hoocon-submit-menu__trigger");
    if (!panel || !trigger) {
      return;
    }

    var rect = trigger.getBoundingClientRect();
    var inset = VIEWPORT_INSET_PX;
    var maxWidth = Math.max(160, window.innerWidth - inset * 2);
    panel.style.width = Math.min(panel.offsetWidth || maxWidth, maxWidth) + "px";

    var panelWidth = panel.offsetWidth;
    var panelHeight = panel.offsetHeight;
    var left = rect.right - panelWidth;
    if (left < inset) {
      left = inset;
    }
    if (left + panelWidth > window.innerWidth - inset) {
      left = window.innerWidth - inset - panelWidth;
    }

    var spaceAbove = rect.top - inset;
    var spaceBelow = window.innerHeight - rect.bottom - inset;
    var nearBottom = rect.bottom > window.innerHeight - 96;
    var openAbove = nearBottom || spaceAbove >= spaceBelow;

    panel.style.position = "fixed";
    panel.style.left = left + "px";
    panel.style.right = "auto";
    if (openAbove) {
      panel.style.bottom =
        Math.max(inset, window.innerHeight - rect.top + PANEL_GAP_PX) + "px";
      panel.style.top = "auto";
    } else {
      panel.style.top =
        Math.min(window.innerHeight - inset - panelHeight, rect.bottom + PANEL_GAP_PX) + "px";
      panel.style.bottom = "auto";
    }
  }

  function closeMenu() {
    if (!state.menu) {
      return;
    }
    var panel = state.menu.querySelector(".hoocon-submit-menu__panel");
    var trigger = state.menu.querySelector(".hoocon-submit-menu__trigger");
    if (panel) {
      panel.setAttribute("hidden", "");
      resetPanelPosition(panel);
    }
    if (trigger) {
      trigger.setAttribute("aria-expanded", "false");
    }
    state.menu.classList.remove("is-open");
    state.open = false;
  }

  function openMenu() {
    if (!state.menu) {
      return;
    }
    var panel = state.menu.querySelector(".hoocon-submit-menu__panel");
    var trigger = state.menu.querySelector(".hoocon-submit-menu__trigger");
    if (!panel || !trigger) {
      return;
    }
    panel.removeAttribute("hidden");
    trigger.setAttribute("aria-expanded", "true");
    state.menu.classList.add("is-open");
    state.open = true;
    window.requestAnimationFrame(positionOpenPanel);
  }

  function onResizeWhileOpen() {
    if (state.open) {
      positionOpenPanel();
    }
  }

  function toggleMenu() {
    if (state.open) {
      closeMenu();
    } else {
      openMenu();
    }
  }

  function onDocumentClick(event) {
    if (!state.menu || !state.open) {
      return;
    }
    if (state.menu.contains(event.target)) {
      return;
    }
    closeMenu();
  }

  function onKeyDown(event) {
    if (event.key === "Escape") {
      closeMenu();
    }
  }

  function buildMenu(container, buttons) {
    if (buttons.length < 2 || state.menu) {
      return;
    }

    /* Anchor before moving nodes — appendChild detaches buttons from .container. */
    var anchor = buttons[0];

    var menu = document.createElement("div");
    menu.className = MENU_CLASS;
    menu.setAttribute("data-hoocon-submit-menu", "");

    var trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "hoocon-submit-menu__trigger " + unfoldTriggerClasses(buttons[0]);
    trigger.setAttribute("aria-haspopup", "menu");
    trigger.setAttribute("aria-expanded", "false");
    var primaryLabel = (buttons[0].textContent || "").trim() || "Сохранить";
    trigger.innerHTML =
      '<span class="hoocon-submit-menu__trigger-label">' +
      primaryLabel +
      '</span><span class="material-symbols-outlined hoocon-submit-menu__chevron" aria-hidden="true">' +
      "expand_more</span>";

    var panel = document.createElement("div");
    panel.className = "hoocon-submit-menu__panel";
    panel.setAttribute("role", "menu");
    panel.setAttribute("hidden", "");

    trigger.addEventListener("click", function (event) {
      event.preventDefault();
      toggleMenu();
    });

    menu.appendChild(trigger);
    menu.appendChild(panel);
    container.insertBefore(menu, anchor);

    buttons.forEach(function (btn) {
      btn.classList.add("hoocon-submit-menu__action");
      btn.addEventListener("click", closeMenu);
      panel.appendChild(btn);
    });

    container.classList.add(ACTIVE_CLASS);
    state.container = container;
    state.menu = menu;

    document.addEventListener("click", onDocumentClick, true);
    document.addEventListener("keydown", onKeyDown);
  }

  function destroyMenu() {
    closeMenu();
    if (!state.menu || !state.container) {
      state.container = null;
      state.menu = null;
      return;
    }

    var panel = state.menu.querySelector(".hoocon-submit-menu__panel");
    var buttons = panel ? Array.from(panel.querySelectorAll("button[name]")) : [];
    var parent = state.menu.parentNode || state.container;
    buttons.forEach(function (btn) {
      btn.classList.remove("hoocon-submit-menu__action");
      if (parent) {
        parent.insertBefore(btn, state.menu);
      }
    });
    state.menu.remove();
    state.container.classList.remove(ACTIVE_CLASS);
    state.container = null;
    state.menu = null;

    document.removeEventListener("click", onDocumentClick, true);
    document.removeEventListener("keydown", onKeyDown);
  }

  function sync() {
    if (!isChangeForm()) {
      destroyMenu();
      return;
    }

    var container = getContainer();
    if (!container) {
      destroyMenu();
      return;
    }

    var buttons = getSaveButtons(container);
    if (!buttons.length) {
      destroyMenu();
      return;
    }

    if (rowNeedsCollapse(container, buttons)) {
      if (!state.menu) {
        buildMenu(container, buttons);
      }
      return;
    }

    if (state.menu) {
      destroyMenu();
      window.requestAnimationFrame(sync);
    }
  }

  function observeContainer() {
    if (state.observer) {
      state.observer.disconnect();
      state.observer = null;
    }
    if (state.mutator) {
      state.mutator.disconnect();
      state.mutator = null;
    }

    var container = getContainer();
    var row = document.getElementById("submit-row");
    if (!container) {
      return;
    }

    if (typeof ResizeObserver === "function") {
      state.observer = new ResizeObserver(function () {
        sync();
      });
      state.observer.observe(container);
      if (row) {
        state.observer.observe(row);
      }
    }

    if (typeof MutationObserver === "function" && row) {
      state.mutator = new MutationObserver(function () {
        sync();
      });
      state.mutator.observe(row, { childList: true, subtree: true });
    }
  }

  function boot() {
    sync();
    observeContainer();
    window.addEventListener("resize", sync, { passive: true });
    window.addEventListener("resize", onResizeWhileOpen, { passive: true });
    window.setTimeout(sync, 0);
    window.setTimeout(sync, 200);

    var media = tabletMq();
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", sync);
    } else if (typeof media.addListener === "function") {
      media.addListener(sync);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
