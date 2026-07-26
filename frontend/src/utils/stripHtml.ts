/**
 * Strip HTML tags and decode entities for plain-text excerpts / reading time.
 * Mirrors backend ``strip_html_to_text`` (content.etl.tilda_articles).
 */
const NAMED_ENTITIES: Record<string, string> = {
  nbsp: "\u00A0",
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  mdash: "\u2014",
  ndash: "\u2013",
  hellip: "\u2026",
  middot: "\u00B7",
};

function decodeHtmlEntities(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (full, ent: string) => {
    const lower = ent.toLowerCase();
    if (lower.startsWith("#x")) {
      const code = Number.parseInt(lower.slice(2), 16);
      return Number.isFinite(code) ? String.fromCodePoint(code) : full;
    }
    if (lower.startsWith("#")) {
      const code = Number.parseInt(lower.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : full;
    }
    return NAMED_ENTITIES[lower] ?? full;
  });
}

export function stripHtmlToText(html: string): string {
  const withoutTags = (html || "").replace(/<[^>]+>/g, " ");
  return decodeHtmlEntities(withoutTags).replace(/\s+/g, " ").trim();
}
