import { Fragment, type ReactNode } from "react";

import { softBreakParts } from "../utils/softBreak";

/**
 * Render text with soft wraps; atomic chunks use ``white-space: nowrap``.
 *
 * Survives ``word-break: break-word`` (unlike WORD JOINER alone).
 */
export function SoftBreakText({ text }: { text: string }): ReactNode {
  const parts = softBreakParts(text);
  if (parts.length === 0) {
    return null;
  }
  return parts.map((part, index) =>
    part.nowrap ? (
      <span key={index} className="u-nowrap">
        {part.text}
      </span>
    ) : (
      <Fragment key={index}>{part.text}</Fragment>
    ),
  );
}
