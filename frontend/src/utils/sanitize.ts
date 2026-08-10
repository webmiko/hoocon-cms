import DOMPurify from "dompurify";

import { wrapCmsTables } from "./wrapCmsTables";

const ALLOWED_TAGS = [
  "p", "br", "strong", "em", "u", "s", "a", "ul", "ol", "li",
  // h1 stripped: page template already owns the document H1
  "h2", "h3", "h4", "h5", "h6",
  "table", "thead", "tbody", "tr", "th", "td",
  "img", "figure", "figcaption",
  "blockquote", "pre", "code",
  "div", "span",
];

const ALLOWED_ATTR = [
  "href",
  "src",
  "alt",
  "title",
  "class",
  "id", // TOC / FAQ in-page anchors (#section)
  "target",
  "rel",
  "loading",
  "decoding",
  "width",
  "height",
];

/**
 * Downgrade CMS ``<h1>`` to ``<h2>`` before purify so the SPA page H1 stays unique.
 *
 * Args:
 *   html: Raw CMS HTML.
 *
 * Returns:
 *   HTML with h1 tags rewritten to h2 (attributes preserved on open tags).
 */
export function downgradeCmsH1(html: string): string {
  return html
    .replace(/<\s*h1(\s[^>]*)?>/gi, "<h2$1>")
    .replace(/<\s*\/\s*h1\s*>/gi, "</h2>");
}

export function sanitizeHtml(html: string): string {
  const withSingleH1 = downgradeCmsH1(html);
  const clean = DOMPurify.sanitize(withSingleH1, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
  });
  return wrapCmsTables(clean);
}
