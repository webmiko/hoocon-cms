/**
 * Queue switch on each manager's group. Companies are already rendered
 * under that manager; this only saves the one switch.
 */
(function () {
  "use strict";

  function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  document.addEventListener("DOMContentLoaded", function () {
    const board = document.querySelector(".hoocon-pinned-board");
    if (!board) {
      return;
    }
    const url = board.getAttribute("data-url") || "";
    board.querySelectorAll(".hoocon-pinned-manager").forEach(function (section) {
      const input = section.querySelector("input.hoocon-toggle");
      const id = section.getAttribute("data-assignee-id") || "";
      if (!input || !id || !url) {
        return;
      }
      const saved = section.querySelector(".hoocon-pinned-manager__saved");
      let savedTimer = 0;
      input.addEventListener("change", function () {
        const body = new URLSearchParams();
        body.set("assignee", id);
        body.set("pinned_only", input.checked ? "1" : "0");
        if (saved) {
          saved.hidden = true;
        }
        window.clearTimeout(savedTimer);
        fetch(url, {
          method: "POST",
          headers: {
            "X-CSRFToken": csrfToken(),
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: body.toString(),
          credentials: "same-origin",
        })
          .then(function (response) {
            if (!response.ok) {
              input.checked = !input.checked;
              return;
            }
            if (saved) {
              saved.hidden = false;
              savedTimer = window.setTimeout(function () {
                saved.hidden = true;
              }, 2000);
            }
          })
          .catch(function () {
            input.checked = !input.checked;
            if (saved) {
              saved.hidden = true;
            }
          });
      });
    });
  });
})();
