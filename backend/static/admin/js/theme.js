"use strict";
{
  const STORAGE_KEY = "theme";
  const SYSTEM_DARK_QUERY = "(prefers-color-scheme: dark)";

  function systemDark() {
    return typeof window.matchMedia === "function" &&
      window.matchMedia(SYSTEM_DARK_QUERY).matches;
  }

  function resolveTheme(mode) {
    if (mode === "light") {
      return "light";
    }
    if (mode === "dark") {
      return "dark";
    }
    return systemDark() ? "dark" : "light";
  }

  function readPreference() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "auto") {
      return stored;
    }
    return "auto";
  }

  function applyTheme(mode) {
    if (mode !== "light" && mode !== "dark" && mode !== "auto") {
      console.error(`Got invalid theme mode: ${mode}. Resetting to auto.`);
      mode = "auto";
    }
    // data-theme-mode — выбор пользователя (auto/light/dark);
    // data-theme — resolved light|dark для CSS.
    document.documentElement.dataset.themeMode = mode;
    document.documentElement.dataset.theme = resolveTheme(mode);
    localStorage.setItem(STORAGE_KEY, mode);
  }

  function cycleTheme() {
    const currentTheme = readPreference();
    if (currentTheme === "auto") {
      applyTheme("light");
    } else if (currentTheme === "light") {
      applyTheme("dark");
    } else {
      applyTheme("auto");
    }
  }

  function bindToggles() {
    const buttons = document.getElementsByClassName("theme-toggle");
    Array.from(buttons).forEach((btn) => {
      if (!btn.dataset.themeBound) {
        btn.addEventListener("click", cycleTheme);
        btn.dataset.themeBound = "1";
      }
    });
  }

  function initTheme() {
    applyTheme(readPreference());
  }

  function watchSystemTheme() {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const media = window.matchMedia(SYSTEM_DARK_QUERY);
    const sync = () => {
      if (readPreference() === "auto") {
        document.documentElement.dataset.theme = resolveTheme("auto");
      }
    };
    media.addEventListener("change", sync);
  }

  // Привязываем клики как только DOM готов, не ждём полной загрузки ресурсов.
  function onReady(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback);
    } else {
      callback();
    }
  }

  onReady(bindToggles);
  initTheme();
  watchSystemTheme();
}
