/**
 * Poll new-leads count for the Admin header sticker.
 * Script tag must carry data-count-url (staff-only JSON endpoint).
 */
(function () {
  "use strict";

  const script = document.currentScript;
  const countUrl = script && script.getAttribute("data-count-url");
  const pollMs = Number(script && script.getAttribute("data-poll-ms")) || 60000;
  const sticker = document.getElementById("hoocon-admin-lead-sticker");
  const countEl = document.querySelector("[data-hoocon-new-leads-count]");

  if (!countUrl || !sticker || !countEl) {
    return;
  }

  /**
   * @param {number} count
   */
  function applyCount(count) {
    const safe = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
    countEl.textContent = String(safe);
    sticker.classList.toggle("hoocon-admin-lead-sticker--active", safe > 0);
    sticker.setAttribute("aria-label", "Новые непросмотренные заявки: " + safe);
    sticker.hidden = safe === 0;
  }

  async function refresh() {
    try {
      const response = await fetch(countUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      applyCount(Number(data.count) || 0);
    } catch (_err) {
      // Ignore transient network errors; next poll will retry.
    }
  }

  applyCount(Number(countEl.textContent) || 0);
  window.setInterval(refresh, pollMs);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refresh();
    }
  });
})();
