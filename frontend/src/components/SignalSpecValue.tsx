import { Link } from "react-router-dom";

import { SoftBreakText } from "./SoftBreakText";

/** FAQ section explaining current-mode special order (seed_site_content). */
export const SIGNAL_MA_SPECIAL_ORDER_HREF = "/faq#signal-ma-special-order";

const SPECIAL_ORDER_MARK = "(спецзаказ)";

interface SignalSpecValueProps {
  value: string;
  /** When true, «спецзаказ» is a link (PDP / card footnote — not nested in <a>). */
  linkNote?: boolean;
  /** Warehouse has 4–20 mA (special-order) units for this SKU. */
  maInStock?: boolean;
  className?: string;
}

/**
 * Render Y/U signal value; turn «(спецзаказ)» into FAQ link when allowed.
 */
export function SignalSpecValue({
  value,
  linkNote = true,
  maInStock = false,
  className,
}: SignalSpecValueProps) {
  const idx = value.indexOf(SPECIAL_ORDER_MARK);
  if (idx < 0 || !linkNote) {
    return (
      <span className={className}>
        <SoftBreakText text={value} />
      </span>
    );
  }

  const before = value.slice(0, idx);
  const after = value.slice(idx + SPECIAL_ORDER_MARK.length);
  const pillClass = maInStock
    ? "signalSpecNotePill signalSpecNotePillInStock"
    : "signalSpecNotePill";
  const noteLabel = maInStock ? "спецзаказ · на складе" : "спецзаказ";

  return (
    <span className={className}>
      {before ? <SoftBreakText text={before} /> : null}
      <span className={pillClass}>
        <Link
          to={SIGNAL_MA_SPECIAL_ORDER_HREF}
          className="signalSpecNoteLink"
          onClick={(event) => {
            event.stopPropagation();
          }}
        >
          {noteLabel}
        </Link>
      </span>
      {after ? <SoftBreakText text={after} /> : null}
    </span>
  );
}
