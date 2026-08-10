/**
 * Wrap bare CMS <table> nodes in .table-scroll for overflow-x (ArticlePage CSS).
 * Idempotent when tables are already wrapped.
 */

const TABLE_OR_WRAPPED_RE =
  /<div\s+[^>]*\btable-scroll\b[^>]*>\s*<table\b[\s\S]*?<\/table>\s*<\/div>|<table\b[\s\S]*?<\/table>/gi;

export function wrapCmsTables(html: string): string {
  if (!html || !html.includes("<table")) {
    return html;
  }
  return html.replace(TABLE_OR_WRAPPED_RE, (match) =>
    match.startsWith("<div") ? match : `<div class="table-scroll">${match}</div>`,
  );
}
