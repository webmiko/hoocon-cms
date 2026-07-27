/**
 * Extract h2/h3 headings from sanitized article HTML and inject stable ids.
 * Spec: ПЛАН Iter 6 — Article TOC.
 */

export interface ArticleTocItem {
  id: string;
  text: string;
  level: 2 | 3;
}

const HEADING_RE = /<(h[23])(\s[^>]*)?>([\s\S]*?)<\/\1>/gi;

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function slugifyHeading(text: string, used: Set<string>): string {
  const base =
    text
      .toLowerCase()
      .replace(/ё/g, "е")
      .replace(/[^a-z0-9а-я]+/gi, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64) || "section";
  let id = base;
  let n = 2;
  while (used.has(id)) {
    id = `${base}-${n}`;
    n += 1;
  }
  used.add(id);
  return id;
}

/**
 * Returns TOC items and HTML with id attributes on h2/h3.
 *
 * Args:
 *   html: Already-sanitized article body HTML.
 *
 * Returns:
 *   `{ html, items }` — hide TOC when items.length < 3.
 */
export function extractArticleToc(html: string): {
  html: string;
  items: ArticleTocItem[];
} {
  if (!html) {
    return { html: "", items: [] };
  }
  const used = new Set<string>();
  const items: ArticleTocItem[] = [];
  const next = html.replace(HEADING_RE, (full, tag: string, attrs = "", inner: string) => {
    const level = tag.toLowerCase() === "h2" ? 2 : 3;
    const text = stripTags(inner);
    if (!text) {
      return full;
    }
    const existing = /\sid\s*=\s*["']([^"']+)["']/i.exec(attrs || "");
    const id = existing?.[1] || slugifyHeading(text, used);
    if (!existing) {
      used.add(id);
    } else {
      used.add(id);
    }
    items.push({ id, text, level: level as 2 | 3 });
    const cleanAttrs = (attrs || "").replace(/\s+id\s*=\s*["'][^"']*["']/i, "");
    return `<${tag}${cleanAttrs} id="${id}">${inner}</${tag}>`;
  });
  return { html: next, items };
}
