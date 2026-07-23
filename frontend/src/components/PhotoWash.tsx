import type { CSSProperties, ReactNode } from "react";

import { useMatchedPhotoWash } from "../hooks/useMatchedPhotoWash";

type PhotoWashProps = {
  /** Product photo URL to sample; omit for CSS purpose fallback only. */
  src?: string | null;
  className?: string;
  /** Category purpose wash until/unless sampling succeeds. */
  "data-purpose"?: string;
  /**
   * ``auto`` — sample cutout edge wash (product photos).
   * ``white`` — solid white (wiring / dimension diagrams from manuals).
   */
  backdrop?: "auto" | "white";
  style?: CSSProperties;
  children?: ReactNode;
};

/**
 * Media cell that paints a wash matching the photo edge backdrop per SKU.
 *
 * Uses a multi-stop left→right gradient from sampled top-edge colors. Falls
 * back to ``data-purpose`` token washes when sampling is unavailable.
 * Diagram tiles use ``backdrop="white"`` so schematics stay on paper white.
 */
export function PhotoWash({
  src,
  className,
  style,
  children,
  backdrop = "auto",
  "data-purpose": purpose,
}: PhotoWashProps) {
  const wash = useMatchedPhotoWash(backdrop === "white" ? null : src);
  const mergedStyle: CSSProperties | undefined =
    backdrop === "white"
      ? { ...style, background: "#fff" }
      : wash
        ? { ...style, background: wash.css }
        : style;

  return (
    <div
      className={className}
      data-purpose={purpose}
      data-backdrop={backdrop}
      style={mergedStyle}
    >
      {children}
    </div>
  );
}
