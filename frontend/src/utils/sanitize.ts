import DOMPurify from "dompurify";

import { wrapCmsTables } from "./wrapCmsTables";

const ALLOWED_TAGS = [
  "p", "br", "strong", "em", "u", "s", "a", "ul", "ol", "li",
  "h1", "h2", "h3", "h4", "h5", "h6",
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

export function sanitizeHtml(html: string): string {
  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
  });
  return wrapCmsTables(clean);
}
