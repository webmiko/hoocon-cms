import type { ReactNode } from "react";

import { softBreak } from "../utils/softBreak";
import { highlightQuerySegments } from "../utils/highlightQuery";

type HighlightQueryProps = {
  text: string;
  query: string;
  /** Optional class on ``<mark>`` hits (e.g. CSS module). */
  markClassName?: string;
};

/**
 * Render plain text with query matches wrapped in ``<mark>``.
 *
 * Soft-breaks each segment so long SKU titles still wrap safely.
 *
 * Args:
 *   text: Title or snippet from search results.
 *   query: Active search query.
 *   markClassName: Optional mark styling class.
 *
 * Returns:
 *   React nodes (string segments and ``<mark>`` elements).
 */
export function HighlightQuery({
  text,
  query,
  markClassName,
}: HighlightQueryProps): ReactNode {
  const segments = highlightQuerySegments(text, query);
  if (segments.length === 1 && !segments[0]?.match) {
    return softBreak(text);
  }

  return segments.map((segment, index) => {
    const body = softBreak(segment.text);
    if (!segment.match) {
      return <span key={index}>{body}</span>;
    }
    return (
      <mark key={index} className={markClassName}>
        {body}
      </mark>
    );
  });
}
