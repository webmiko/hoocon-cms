/**
 * Leads changelist board: wall status headers + kanban columns + DnD status.
 * Expects body.hoocon-lead-board and data-hoocon-lead-view=wall|kanban.
 *
 * Unfold renders each result row in its own <tbody> — collect rows across all.
 */
(function () {
  "use strict";

  const STATUS_ORDER = ["new", "in_progress", "done"];
  const STATUS_LABELS = {
    new: "Новая",
    in_progress: "В работе",
    done: "Завершена",
  };
  const BOARD_BUILT = "data-hoocon-lead-board-built";
  const DRAG_MIME = "application/x-hoocon-lead-pk";

  function leadView() {
    const toggle = document.querySelector(".hoocon-lead-view-toggle");
    const fromToggle = toggle && toggle.getAttribute("data-hoocon-lead-view");
    const raw = (fromToggle || document.body.dataset.hooconLeadView || "wall").toLowerCase();
    const view = raw === "kanban" ? "kanban" : "wall";
    document.body.dataset.hooconLeadView = view;
    return view;
  }

  function isPhone() {
    return window.matchMedia("(max-width: 767px)").matches;
  }

  function leadTable() {
    return document.querySelector(
      "#changelist table.hoocon-admin-card-table, #changelist table",
    );
  }

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  /**
   * @param {HTMLTableElement} table
   * @returns {HTMLTableRowElement[]}
   */
  function dataRows(table) {
    return Array.from(table.querySelectorAll("tbody tr")).filter(function (row) {
      return !row.classList.contains("hoocon-lead-wall-heading");
    });
  }

  /**
   * @param {HTMLTableRowElement} row
   * @returns {string}
   */
  function rowStatus(row) {
    const badge = row.querySelector(
      ".hoocon-lead-status--new, .hoocon-lead-status--in_progress, .hoocon-lead-status--done",
    );
    if (!badge) {
      return "new";
    }
    if (badge.classList.contains("hoocon-lead-status--done")) {
      return "done";
    }
    if (badge.classList.contains("hoocon-lead-status--in_progress")) {
      return "in_progress";
    }
    return "new";
  }

  /**
   * @param {HTMLTableRowElement} row
   * @returns {string}
   */
  function rowPk(row) {
    const box = row.querySelector("input.action-select[value], input.action-select");
    if (box && box.value) {
      return String(box.value);
    }
    const open = row.querySelector("a.hoocon-admin-lead-open, a[href*='/change/']");
    if (open && open.getAttribute("href")) {
      const m = open.getAttribute("href").match(/\/lead\/(\d+)\/change\//);
      if (m) {
        return m[1];
      }
    }
    return "";
  }

  /**
   * @param {HTMLTableRowElement} row
   * @param {string} status
   */
  function setRowStatusBadge(row, status) {
    const badge = row.querySelector(".hoocon-lead-status");
    if (!badge) {
      return;
    }
    STATUS_ORDER.forEach(function (key) {
      badge.classList.remove("hoocon-lead-status--" + key);
    });
    badge.classList.add("hoocon-lead-status--" + status);
    badge.textContent = STATUS_LABELS[status] || status;
  }

  /**
   * @param {HTMLElement} board
   */
  function recountKanban(board) {
    board.querySelectorAll(".hoocon-lead-kanban__col").forEach(function (col) {
      const n = col.querySelectorAll(".hoocon-lead-kanban__cards > tr").length;
      const count = col.querySelector(".hoocon-lead-kanban__count");
      if (count) {
        count.textContent = String(n);
      }
    });
  }

  /**
   * @param {string} pk
   * @param {string} status
   * @returns {Promise<{ok: boolean, status?: string, error?: string, http: number}>}
   */
  function postLeadStatus(pk, status) {
    return fetch("/admin/leads/lead/" + encodeURIComponent(pk) + "/set-status/", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ status: status }),
    }).then(function (res) {
      return res.json().then(
        function (data) {
          return {
            ok: Boolean(data && data.ok),
            status: data && data.status,
            error: data && data.error,
            http: res.status,
          };
        },
        function () {
          return { ok: false, error: "invalid_json", http: res.status };
        },
      );
    });
  }

  /**
   * @param {HTMLElement} board
   */
  function enableKanbanDragDrop(board) {
    let dragRow = null;
    let originCards = null;
    let originNext = null;

    board.querySelectorAll(".hoocon-lead-kanban__cards > tr").forEach(function (row) {
      if (!rowPk(row)) {
        return;
      }
      row.setAttribute("draggable", "true");
      row.addEventListener("dragstart", function (event) {
        const target = event.target;
        if (
          target instanceof Element &&
          target.closest("a, button, input, label, select, textarea")
        ) {
          event.preventDefault();
          return;
        }
        dragRow = row;
        originCards = row.parentElement;
        originNext = row.nextElementSibling;
        row.classList.add("hoocon-lead-kanban__dragging");
        row.setAttribute("data-hoocon-just-dragged", "1");
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData(DRAG_MIME, rowPk(row));
          event.dataTransfer.setData("text/plain", rowPk(row));
        }
      });
      row.addEventListener("dragend", function () {
        row.classList.remove("hoocon-lead-kanban__dragging");
        board.querySelectorAll(".hoocon-lead-kanban__drop-target").forEach(function (col) {
          col.classList.remove("hoocon-lead-kanban__drop-target");
        });
        window.setTimeout(function () {
          row.removeAttribute("data-hoocon-just-dragged");
        }, 400);
        dragRow = null;
        originCards = null;
        originNext = null;
      });
    });

    board.querySelectorAll(".hoocon-lead-kanban__col").forEach(function (col) {
      const status = col.dataset.status || "";
      const cards = col.querySelector(".hoocon-lead-kanban__cards");
      if (!cards || STATUS_ORDER.indexOf(status) < 0) {
        return;
      }

      col.addEventListener("dragover", function (event) {
        if (!dragRow) {
          return;
        }
        event.preventDefault();
        if (event.dataTransfer) {
          event.dataTransfer.dropEffect = "move";
        }
        col.classList.add("hoocon-lead-kanban__drop-target");
      });

      col.addEventListener("dragleave", function (event) {
        if (!col.contains(event.relatedTarget)) {
          col.classList.remove("hoocon-lead-kanban__drop-target");
        }
      });

      col.addEventListener("drop", function (event) {
        event.preventDefault();
        col.classList.remove("hoocon-lead-kanban__drop-target");
        if (!dragRow) {
          return;
        }
        const pk = rowPk(dragRow);
        const fromStatus = rowStatus(dragRow);
        if (!pk || status === fromStatus) {
          return;
        }

        const moving = dragRow;
        const backParent = originCards;
        const backNext = originNext;
        cards.appendChild(moving);
        setRowStatusBadge(moving, status);
        recountKanban(board);

        postLeadStatus(pk, status)
          .then(function (result) {
            if (result.ok) {
              return;
            }
            if (backParent) {
              if (backNext && backNext.parentElement === backParent) {
                backParent.insertBefore(moving, backNext);
              } else {
                backParent.appendChild(moving);
              }
            }
            setRowStatusBadge(moving, fromStatus);
            recountKanban(board);
            if (result.http === 409) {
              window.alert("Заявку уже взял другой менеджер.");
            } else {
              window.alert("Не удалось сменить статус заявки.");
            }
          })
          .catch(function () {
            if (backParent) {
              if (backNext && backNext.parentElement === backParent) {
                backParent.insertBefore(moving, backNext);
              } else {
                backParent.appendChild(moving);
              }
            }
            setRowStatusBadge(moving, fromStatus);
            recountKanban(board);
            window.alert("Не удалось сменить статус заявки.");
          });
      });
    });
  }

  function clearWallHeadings(table) {
    table.querySelectorAll("tr.hoocon-lead-wall-heading").forEach(function (row) {
      row.remove();
    });
  }

  /**
   * Insert full-width status section titles between card groups (wall mode).
   *
   * @param {HTMLTableElement} table
   */
  function applyWallHeadings(table) {
    clearWallHeadings(table);
    let last = null;
    dataRows(table).forEach(function (row) {
      const status = rowStatus(row);
      if (status === last) {
        return;
      }
      last = status;
      const heading = document.createElement("tr");
      heading.className = "hoocon-lead-wall-heading";
      heading.setAttribute("aria-hidden", "true");
      const cell = document.createElement("td");
      cell.colSpan = 99;
      cell.textContent = STATUS_LABELS[status] || status;
      heading.appendChild(cell);
      const parent = row.parentElement;
      if (parent) {
        parent.insertBefore(heading, row);
      }
    });
  }

  /**
   * Build three status columns and move card rows into them.
   *
   * @param {HTMLTableElement} table
   */
  function applyKanban(table) {
    const results = table.closest(".results") || table.parentElement;
    if (!results) {
      return;
    }

    // Re-entrant: delayed/resize refresh must not discard rows already in the board.
    restoreRowsToTable(table);
    clearWallHeadings(table);

    const rows = dataRows(table);
    if (!rows.length && !table.tBodies.length) {
      return;
    }

    const board = document.createElement("div");
    board.className = "hoocon-lead-kanban";
    board.setAttribute(BOARD_BUILT, "1");

    /** @type {Record<string, {col: HTMLElement, cards: HTMLElement, count: HTMLElement}>} */
    const cols = {};
    STATUS_ORDER.forEach(function (status) {
      const col = document.createElement("div");
      col.className = "hoocon-lead-kanban__col";
      col.dataset.status = status;

      const head = document.createElement("div");
      head.className = "hoocon-lead-kanban__head";
      const title = document.createElement("span");
      title.textContent = STATUS_LABELS[status];
      const count = document.createElement("span");
      count.className = "hoocon-lead-kanban__count";
      count.textContent = "0";
      head.appendChild(title);
      head.appendChild(count);

      const cards = document.createElement("div");
      cards.className = "hoocon-lead-kanban__cards";

      col.appendChild(head);
      col.appendChild(cards);
      board.appendChild(col);
      cols[status] = { col: col, cards: cards, count: count };
    });

    rows.forEach(function (row) {
      const status = rowStatus(row);
      const bucket = cols[status] || cols.new;
      bucket.cards.appendChild(row);
    });

    STATUS_ORDER.forEach(function (status) {
      const n = cols[status].cards.querySelectorAll("tr").length;
      cols[status].count.textContent = String(n);
    });

    table.classList.add("hoocon-lead-kanban-source");
    results.appendChild(board);
    enableKanbanDragDrop(board);
  }

  function restoreRowsToTable(table) {
    const results = table.closest(".results") || table.parentElement;
    if (!results) {
      return;
    }
    const board = results.querySelector(".hoocon-lead-kanban");
    if (!board) {
      table.classList.remove("hoocon-lead-kanban-source");
      return;
    }
    const rows = Array.from(board.querySelectorAll(".hoocon-lead-kanban__cards > tr"));
    rows.forEach(function (row, index) {
      let tbody = table.tBodies[index];
      if (!tbody) {
        tbody = document.createElement("tbody");
        table.appendChild(tbody);
      }
      tbody.appendChild(row);
    });
    board.remove();
    table.classList.remove("hoocon-lead-kanban-source");
  }

  function refreshBoard() {
    if (!document.body.classList.contains("hoocon-lead-board")) {
      return;
    }
    const table = leadTable();
    if (!table || !table.tBodies.length) {
      return;
    }

    const view = leadView();
    const phone = isPhone();

    // Kanban is desktop-only; phone always uses the stacked wall card list.
    if (view === "kanban" && !phone) {
      applyKanban(table);
      return;
    }

    restoreRowsToTable(table);
    if (!phone) {
      applyWallHeadings(table);
    } else {
      clearWallHeadings(table);
    }
  }

  function scheduleRefresh() {
    window.requestAnimationFrame(function () {
      refreshBoard();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!document.body.classList.contains("hoocon-lead-board")) {
      return;
    }
    if (!document.body.dataset.hooconLeadView) {
      document.body.dataset.hooconLeadView = "wall";
    }
    scheduleRefresh();
    // Tables JS stacks asynchronously / on resize — re-run after settle.
    window.setTimeout(scheduleRefresh, 50);
    window.setTimeout(scheduleRefresh, 400);
    window.addEventListener("resize", scheduleRefresh);
  });
})();
