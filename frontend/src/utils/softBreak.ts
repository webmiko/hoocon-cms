/**
 * Smart line-break helpers for long SKU / catalog strings.
 *
 * Inserts zero-width spaces (U+200B) after natural separators so the browser
 * wraps at `|`, `/`, `-`, etc. instead of mid-word or overflowing the layout.
 * Edition suffixes and factory notes stay on one line via nowrap parts.
 * Opening/closing parentheses stay glued to adjacent text (never alone on a line).
 */

/** Soft wrap *after* these marks — never ``(`` / ``)`` / brackets (glued separately). */
const BREAK_AFTER = /([|/\\·•—–_,;:])/g;
const BREAK_AFTER_HYPHEN = /(-)(?=[^\s-])/g;

/** Zero-width Word Joiner — keeps ``(`` / ``)`` attached to neighboring text. */
const WORD_JOINER = "\u2060";

/**
 * Candidate parenthetical spans (not bare ``(2)``).
 * Only a subset become nowrap — see :func:`parenChunkIsNowrap`.
 */
const PAREN_CHUNK = /\(\s*(?!\d)[^)]{1,80}\)/gi;

/**
 * Short prose labels kept on one line (e.g. «стандартная серия»).
 * Longer notes like «с шаровидным графитом» must wrap inside narrow ТТХ cards.
 */
const NOWRAP_PAREN_MAX_INNER = 18;

export type SoftBreakPart = {
  text: string;
  /** When true, render with ``white-space: nowrap`` (survives word-break). */
  nowrap: boolean;
};

/**
 * Whether a ``(…)`` span must stay atomic (factory note, edition list, short label).
 *
 * Args:
 *   chunk: Full match including parentheses.
 *
 * Returns:
 *   True when the span should use nowrap / NBSP.
 */
export function parenChunkIsNowrap(chunk: string): boolean {
  const inner = chunk.replace(/^\(\s*|\s*\)$/gu, "").trim();
  if (!inner) return false;
  if (/^Заводская\b/iu.test(inner)) return true;
  if (/В=|мА|\.\.\.|…/u.test(inner)) return true;
  // Edition suffixes: (−D/−DS/−A/−AS), not prose with a slash.
  if (/[−]/.test(inner) || /\/(?:−|[A-Z]{1,4}\d)/.test(inner)) return true;
  return [...inner].length <= NOWRAP_PAREN_MAX_INNER;
}

/**
 * Glue parentheses/brackets to adjacent non-space characters.
 *
 * Args:
 *   text: Segment after punctuation soft-breaks.
 *
 * Returns:
 *   Text with U+2060 so ``(`` / ``)`` never sit alone at a line edge.
 */
function glueParenMarks(text: string): string {
  return text
    .replace(/\((?=\S)/g, `(${WORD_JOINER}`)
    .replace(/(?<=\S)\)/g, `${WORD_JOINER})`)
    .replace(/\[(?=\S)/g, `[${WORD_JOINER}`)
    .replace(/(?<=\S)\]/g, `${WORD_JOINER}]`);
}

/**
 * Apply soft-wrap markers (ZWSP) after punctuation / hyphens.
 *
 * Args:
 *   text: Segment that may wrap at separators.
 *
 * Returns:
 *   Text with U+200B after safe break points; parens glued to neighbors.
 */
function applySoftBreak(text: string): string {
  return glueParenMarks(
    text
      .replace(BREAK_AFTER, "$1\u200B")
      .replace(BREAK_AFTER_HYPHEN, "$1\u200B"),
  );
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
  for (const match of text.matchAll(PAREN_CHUNK)) {
    const start = match.index ?? 0;
    const chunk = match[0] ?? "";
    if (!chunk) continue;
    if (start > last) {
      parts.push({ text: applySoftBreak(text.slice(last, start)), nowrap: false });
    }
    if (parenChunkIsNowrap(chunk)) {
      // Prefer wrapping *before* the whole group.
      parts.push({ text: "\u200B", nowrap: false });
      parts.push({ text: chunk, nowrap: true });
    } else {
      parts.push({ text: applySoftBreak(chunk), nowrap: false });
    }
    last = start + chunk.length;
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
