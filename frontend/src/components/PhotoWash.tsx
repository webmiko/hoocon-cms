import type { CSSProperties, ReactNode } from "react";

type PhotoWashProps = {
  /** Kept for call-site compatibility; theme wash is CSS-only. */
  src?: string | null;
  className?: string;
  /** Category purpose (legacy); all map to ``--photo-wash``. */
  "data-purpose"?: string;
  /**
   * ``auto`` — theme photo wash (light gray / dark graphite).
   * ``white`` — solid white (wiring / dimension diagrams from manuals).
   */
  backdrop?: "auto" | "white";
  style?: CSSProperties;
  children?: ReactNode;
};

/**
 * Media cell with a unified theme wash behind product cutouts.
 *
 * Light: light-gray gradient; dark: graphite. Diagram tiles keep
 * ``backdrop="white"`` so schematics stay on paper.
 */
export function PhotoWash({
  className,
  style,
  children,
  backdrop = "auto",
  "data-purpose": purpose,
}: PhotoWashProps) {
  const mergedStyle: CSSProperties | undefined =
    backdrop === "white" ? { ...style, background: "#fff" } : style;

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
