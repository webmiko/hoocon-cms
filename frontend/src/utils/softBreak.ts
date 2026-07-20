/**
 * Smart line-break helpers for long SKU / catalog strings.
 *
 * Inserts zero-width spaces (U+200B) after natural separators so the browser
 * wraps at `|`, `/`, `-`, etc. instead of mid-word or overflowing the layout.
 * Edition suffixes and factory notes stay on one line via nowrap parts.
 */

const BREAK_AFTER = /([|/\\·•—–_()[\],;:])/g;
const BREAK_AFTER_HYPHEN = /(-)(?=[^\s-])/g;

/** Chunks that must wrap as a single token (edition suffix, factory note). */
const NO_WRAP_CHUNK =
  /\((?:[−-]?[A-Z]{1,4})(?:\s*\/\s*[−-]?[A-Z]{1,4})+\)|\(\s*Заводская установка[^)]*\)|\(\s*спецзаказ\s*\)/gi;

export type SoftBreakPart = {
  text: string;
  /** When true, render with ``white-space: nowrap`` (survives word-break). */
  nowrap: boolean;
};

/**
 * Apply soft-wrap markers (ZWSP) after punctuation / hyphens.
 *
 * Args:
 *   text: Segment that may wrap at separators.
 *
 * Returns:
 *   Text with U+200B after safe break points.
 */
function applySoftBreak(text: string): string {
  return text
    .replace(BREAK_AFTER, "$1\u200B")
    .replace(BREAK_AFTER_HYPHEN, "$1\u200B");
}

/**
 * Split text into soft-breakable and atomic (nowrap) parts.
 *
 * Args:
 *   text: Raw title, code, or attribute value.
 *
 * Returns:
 *   Ordered parts for string join or React render.
 */
export function softBreakParts(text: string): SoftBreakPart[] {
  if (!text) {
    return [];
  }

  const parts: SoftBreakPart[] = [];
  let last = 0;
  for (const match of text.matchAll(NO_WRAP_CHUNK)) {
    const start = match.index ?? 0;
    if (start > last) {
      parts.push({ text: applySoftBreak(text.slice(last, start)), nowrap: false });
    }
    // Prefer wrapping *before* the whole group.
    parts.push({ text: "\u200B", nowrap: false });
    parts.push({ text: match[0], nowrap: true });
    last = start + match[0].length;
  }
  if (last < text.length) {
    parts.push({ text: applySoftBreak(text.slice(last)), nowrap: false });
  }
  return parts.length > 0 ? parts : [{ text: applySoftBreak(text), nowrap: false }];
}

/**
 * Allow soft wraps after punctuation without changing visible text.
 *
 * For UI that needs a plain string (titles in attributes). Prefer
 * ``SoftBreakText`` when nowrap groups must not split under ``word-break``.
 *
 * Args:
 *   text: Raw title, code, or attribute value.
 *
 * Returns:
 *   Same string with U+200B; nowrap chunks use NBSP instead of spaces.
 */
export function softBreak(text: string): string {
  return softBreakParts(text)
    .map((part) => (part.nowrap ? part.text.replaceAll(" ", "\u00A0") : part.text))
    .join("");
}
