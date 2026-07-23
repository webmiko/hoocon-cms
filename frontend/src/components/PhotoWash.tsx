import type { CSSProperties, ReactNode } from "react";

import { useMatchedPhotoWash } from "../hooks/useMatchedPhotoWash";

type PhotoWashProps = {
  /** Product photo URL to sample; omit for CSS purpose fallback only. */
  src?: string | null;
  className?: string;
  /** Category purpose wash until/unless sampling succeeds. */
  "data-purpose"?: string;
  style?: CSSProperties;
  children?: ReactNode;
};

/**
 * Media cell that paints a wash matching the photo edge backdrop per SKU.
 *
 * Uses a multi-stop left→right gradient from sampled top-edge colors. Falls
 * back to ``data-purpose`` token washes when sampling is unavailable.
 */
export function PhotoWash({
  src,
  className,
  style,
  children,
  "data-purpose": purpose,
}: PhotoWashProps) {
  const wash = useMatchedPhotoWash(src);
  const mergedStyle: CSSProperties | undefined = wash
    ? { ...style, background: wash.css }
    : style;

  return (
    <div className={className} data-purpose={purpose} style={mergedStyle}>
      {children}
    </div>
  );
}
