/**
 * Wrap bare CMS <table> nodes in .table-scroll and stamp ``data-label``
 * from ``<th>`` onto body cells (narrow-screen cards in cms-body-charts.css).
 * Idempotent when tables are already wrapped / labelled.
 */

const TABLE_OR_WRAPPED_RE =
  /<div\s+[^>]*\btable-scroll\b[^>]*>\s*<table\b[\s\S]*?<\/table>\s*<\/div>|<table\b[\s\S]*?<\/table>/gi;

const TABLE_RE = /<table\b[\s\S]*?<\/table>/i;

function htmlText(fragment: string): string {
  return fragment
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function headerLabels(tableHtml: string): string[] {
  const thead = /<thead\b[^>]*>([\s\S]*?)<\/thead>/i.exec(tableHtml);
  const source = thead?.[1] ?? "";
  if (source) {
    return [...source.matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/gi)].map((m) =>
      htmlText(m[1]),
    );
  }
  const firstRow = /<tr\b[^>]*>([\s\S]*?)<\/tr>/i.exec(tableHtml);
  if (!firstRow) {
    return [];
  }
  return [...firstRow[1].matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/gi)].map((m) =>
    htmlText(m[1]),
  );
}

function labelRows(html: string, headers: string[]): string {
  return html.replace(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi, (row) => {
    let col = 0;
    return row.replace(/<td(\s[^>]*)?>/gi, (full, attrs = "") => {
      const label = headers[col++];
      if (!label || /\bdata-label\s*=/i.test(attrs)) {
        return full;
      }
      const stamped = attrs
        ? `${attrs} data-label="${escapeAttr(label)}"`
        : ` data-label="${escapeAttr(label)}"`;
      return `<td${stamped}>`;
    });
  });
}

function labelTable(tableHtml: string): string {
  const headers = headerLabels(tableHtml).filter(Boolean);
  if (!headers.length) {
    return tableHtml;
  }
  const tbodyRe = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/i;
  const tbody = tbodyRe.exec(tableHtml);
  if (tbody) {
    const labeled = labelRows(tbody[1], headers);
    return tableHtml.slice(0, tbody.index) +
      tbody[0].replace(tbody[1], labeled) +
      tableHtml.slice(tbody.index + tbody[0].length);
  }
  return tableHtml.replace(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi, (row) => {
    if (/<th\b/i.test(row) && !/<td\b/i.test(row)) {
      return row;
    }
    return labelRows(row, headers);
  });
}

function labelWrappedTables(html: string): string {
  return html.replace(TABLE_RE, (table) => labelTable(table));
}

export function wrapCmsTables(html: string): string {
  if (!html || !html.includes("<table")) {
    return html;
  }
  return html.replace(TABLE_OR_WRAPPED_RE, (match) => {
    const wrapped = match.startsWith("<div")
      ? match
      : `<div class="table-scroll">${match}</div>`;
    return labelWrappedTables(wrapped);
  });
}
