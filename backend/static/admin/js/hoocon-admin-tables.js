/**
 * Адаптивные таблицы Django admin: подписи для card-layout и авто-stack
 * без горизонтального скролла при любой ширине.
 */
(function () {
  "use strict";

  const CARD_TABLE_SELECTORS = [
    "#changelist table",
    ".inline-group .tabular table",
    "table#change-history",
  ];

  const CHECKBOX_LABEL = "Выбрать";
  /* Phones always use cards; wider screens stack when the table cannot fit. */
  const STACK_MQ = "(max-width: 767px)";
  const STACKED_CLASS = "hoocon-admin-table-stacked";
  const CARD_CLASS = "hoocon-admin-card-table";
  /** Extra room so we stack before columns become unreadable. */
  const FIT_SLACK_PX = 12;
  /** Minimum width per data column for a usable table (not cards). */
  const MIN_DATA_COL_PX = 104;
  const MIN_CHECKBOX_COL_PX = 44;

  /** @type {WeakMap<HTMLTableElement, ResizeObserver>} */
  const observers = new WeakMap();

  function cellLabel(headerCell) {
    if (!headerCell) {
      return "";
    }

    if (headerCell.classList.contains("action-checkbox-column")) {
      return CHECKBOX_LABEL;
    }

    const textNode = headerCell.querySelector(".text");
    const raw = (textNode ? textNode.textContent : headerCell.textContent) || "";
    return raw.replace(/\s+/g, " ").trim();
  }

  function headerLabels(table) {
    const headerRow = table.tHead?.rows[0];
    if (!headerRow) {
      return [];
    }

    return Array.from(headerRow.cells, cellLabel);
  }

  function applyRowLabels(row, labels) {
    Array.from(row.cells).forEach((cell, index) => {
      if (cell.hasAttribute("data-label")) {
        return;
      }

      let label = labels[index] || "";
      if (cell.classList.contains("action-checkbox")) {
        label = CHECKBOX_LABEL;
      }

      if (label) {
        cell.setAttribute("data-label", label);
      }
    });
  }

  function fitContainer(table) {
    return (
      table.closest("#changelist-form .results") ||
      table.closest(".inline-group") ||
      table.parentElement
    );
  }

  /**
   * Width needed for readable columns (header labels on one line).
   *
   * tbody is hidden during measure so long cell values do not inflate width.
   * table-layout:fixed + overflow clip hide scrollWidth overflow, so we
   * temporarily measure max-content instead.
   *
   * @param {HTMLTableElement} table
   * @returns {number}
   */
  function measureNaturalTableWidth(table) {
    const headerRow = table.tHead?.rows[0];
    const body = table.tBodies[0];
    if (!headerRow) {
      return table.scrollWidth;
    }

    const styledCells = [];
    const prevLayout = table.style.tableLayout;
    const prevWidth = table.style.width;
    const prevMinWidth = table.style.minWidth;
    const prevBodyDisplay = body ? body.style.display : "";

    if (body) {
      body.style.display = "none";
    }

    table.style.tableLayout = "auto";
    table.style.width = "max-content";
    table.style.minWidth = "max-content";

    Array.from(headerRow.cells).forEach((cell) => {
      styledCells.push([cell, cell.style.whiteSpace]);
      cell.style.whiteSpace = "nowrap";
    });

    void table.offsetWidth;
    const needed = Math.ceil(table.scrollWidth);

    table.style.tableLayout = prevLayout;
    table.style.width = prevWidth;
    table.style.minWidth = prevMinWidth;
    if (body) {
      body.style.display = prevBodyDisplay;
    }
    styledCells.forEach(([cell, whiteSpace]) => {
      cell.style.whiteSpace = whiteSpace;
    });

    return needed;
  }

  /**
   * Comfortable width: headers must fit, and each data column needs a floor.
   *
   * @param {HTMLTableElement} table
   * @returns {number}
   */
  function measureComfortableTableWidth(table) {
    const colCount = table.tHead?.rows[0]?.cells.length || 0;
    const headerNeeded = measureNaturalTableWidth(table);
    const floor =
      colCount > 0 ? MIN_CHECKBOX_COL_PX + Math.max(0, colCount - 1) * MIN_DATA_COL_PX : 0;
    return Math.max(headerNeeded, floor);
  }

  /**
   * Stack into cards when the full table cannot fit the container width.
   *
   * @param {HTMLTableElement} table
   */
  function updateStackMode(table) {
    const container = fitContainer(table);
    if (!container) {
      return;
    }

    if (window.matchMedia(STACK_MQ).matches) {
      table.classList.add(STACKED_CLASS);
      return;
    }

    table.classList.remove(STACKED_CLASS);
    // Force table-mode layout before measuring.
    void table.offsetWidth;

    const available = container.clientWidth;
    const needed = measureComfortableTableWidth(table);
    const overflows = needed > available + FIT_SLACK_PX;

    if (overflows) {
      table.classList.add(STACKED_CLASS);
    } else {
      table.classList.remove(STACKED_CLASS);
    }
  }

  function watchTable(table) {
    if (observers.has(table)) {
      updateStackMode(table);
      return;
    }

    const container = fitContainer(table);
    if (!container || typeof ResizeObserver === "undefined") {
      updateStackMode(table);
      return;
    }

    const observer = new ResizeObserver(() => {
      updateStackMode(table);
    });
    observer.observe(container);
    observer.observe(table);
    observers.set(table, observer);
    updateStackMode(table);
  }

  function applyHeaderTitles(table) {
    table.querySelectorAll("thead th.sortable .text a[role='button']").forEach((link) => {
      const label = (link.textContent || "").replace(/\s+/g, " ").trim();
      if (label && !link.getAttribute("title")) {
        link.setAttribute("title", label);
      }
    });
  }

  function processTable(table) {
    const labels = headerLabels(table);
    if (!labels.length) {
      return;
    }

    table.classList.add(CARD_CLASS);
    applyHeaderTitles(table);

    const body = table.tBodies[0];
    if (!body) {
      return;
    }

    Array.from(body.rows).forEach((row) => applyRowLabels(row, labels));
    watchTable(table);
  }

  function processAllTables(root) {
    CARD_TABLE_SELECTORS.forEach((selector) => {
      root.querySelectorAll(selector).forEach(processTable);
    });
  }

  function observeInlineRows() {
    document.querySelectorAll(`.inline-group .tabular table.${CARD_CLASS}`).forEach((table) => {
      const labels = headerLabels(table);
      if (!labels.length) {
        return;
      }

      const body = table.tBodies[0];
      if (!body) {
        return;
      }

      const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          mutation.addedNodes.forEach((node) => {
            if (node instanceof HTMLTableRowElement && node.parentElement === body) {
              applyRowLabels(node, labels);
            }
          });
        });
        updateStackMode(table);
      });

      observer.observe(body, { childList: true });
    });
  }

  function onViewportChange() {
    document.querySelectorAll(`table.${CARD_CLASS}`).forEach((table) => {
      updateStackMode(table);
    });
  }

  function collapseIdleFilters() {
    const filter = document.getElementById("changelist-filter");
    if (!filter) {
      return;
    }

    filter.querySelectorAll("details").forEach((details) => {
      const selected = details.querySelector("li.selected a");
      const selectedText = (selected?.textContent || "").replace(/\s+/g, " ").trim();
      const isDefaultAll = !selected || selectedText === "Все" || selectedText === "All";
      const optionCount = details.querySelectorAll("li").length;
      // Keep short filters open; collapse long idle ones so the table stays visible.
      if (isDefaultAll && optionCount > 6) {
        details.open = false;
      }
    });
  }

  /**
   * Sidebar / dashboard Add/Change/View links: title + aria-label for tooltips.
   */
  function enhanceSidebarActionTitles() {
    document
      .querySelectorAll(
        "#nav-sidebar a.addlink, #nav-sidebar a.changelink, #nav-sidebar a.viewlink, " +
          "#content-main .module a.addlink, #content-main .module a.changelink, " +
          "#content-main .module a.viewlink",
      )
      .forEach((link) => {
        const label = (link.textContent || "").replace(/\s+/g, " ").trim();
        if (!label) {
          return;
        }
        if (!link.getAttribute("title")) {
          link.setAttribute("title", label);
        }
        if (!link.getAttribute("aria-label")) {
          link.setAttribute("aria-label", label);
        }
      });
  }

  /**
   * Stacked changelist cards: click row (except controls) opens the change link.
   */
  function enableStackedCardNavigation() {
    document.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      if (target.closest("a, button, input, label, select, textarea")) {
        return;
      }
      const row = target.closest(
        "table.hoocon-admin-table-stacked tbody tr",
      );
      if (!row) {
        return;
      }
      const openLink =
        row.querySelector("a.hoocon-admin-lead-open") ||
        row.querySelector("a[href*='/change/']");
      if (!openLink || !(openLink instanceof HTMLAnchorElement)) {
        return;
      }
      event.preventDefault();
      window.location.href = openLink.href;
    });
  }

  function init() {
    processAllTables(document);
    observeInlineRows();
    collapseIdleFilters();
    enhanceSidebarActionTitles();
    enableStackedCardNavigation();
    window.addEventListener("resize", onViewportChange);
    if (typeof window.matchMedia === "function") {
      const mq = window.matchMedia(STACK_MQ);
      if (typeof mq.addEventListener === "function") {
        mq.addEventListener("change", onViewportChange);
      } else if (typeof mq.addListener === "function") {
        mq.addListener(onViewportChange);
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
