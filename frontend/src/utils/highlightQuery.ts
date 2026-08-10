/**
 * Split text into plain / match segments for search-result highlighting.
 *
 * Matches the full query phrase first, then individual tokens (≥ 2 chars).
 * Case-insensitive; safe for user-controlled ``query`` (escaped for RegExp).
 */

export type HighlightSegment = {
  text: string;
  match: boolean;
};

/**
 * Escape RegExp metacharacters in a literal search string.
 *
 * Args:
 *   value: Raw user query fragment.
 *
 * Returns:
 *   Escaped string safe for ``new RegExp``.
 */
export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Build a global case-insensitive pattern for phrase + token matches.
 *
 * Args:
 *   query: Full search string from the URL / form.
 *
 * Returns:
 *   RegExp with capturing group, or ``null`` when nothing to highlight.
 */
export function buildHighlightPattern(query: string): RegExp | null {
  const trimmed = query.trim();
  if (!trimmed) return null;

  const alts = new Set<string>();
  alts.add(escapeRegExp(trimmed));
  for (const token of trimmed.split(/\s+/u)) {
    if (token.length >= 2) {
      alts.add(escapeRegExp(token));
    }
  }

  const ordered = [...alts].sort((a, b) => b.length - a.length);
  if (ordered.length === 0) return null;
  return new RegExp(`(${ordered.join("|")})`, "giu");
}

/**
 * Split ``text`` into consecutive segments flagged as query matches.
 *
 * Args:
 *   text: Title or snippet from the search API (plain text).
 *   query: Current search query.
 *
 * Returns:
 *   Ordered segments covering the whole string (empty → one empty segment).
 */
export function highlightQuerySegments(
  text: string,
  query: string,
): HighlightSegment[] {
  if (!text) {
    return [{ text: "", match: false }];
  }

  const pattern = buildHighlightPattern(query);
  if (!pattern) {
    return [{ text, match: false }];
  }

  const segments: HighlightSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    const hit = match[0] ?? "";
    if (!hit) continue;
    if (start > last) {
      segments.push({ text: text.slice(last, start), match: false });
    }
    segments.push({ text: hit, match: true });
    last = start + hit.length;
  }
  if (last < text.length) {
    segments.push({ text: text.slice(last), match: false });
  }
  return segments.length > 0 ? segments : [{ text, match: false }];
}
