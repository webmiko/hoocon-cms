/**
 * Leads changelist board: wall status headers + kanban columns.
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
