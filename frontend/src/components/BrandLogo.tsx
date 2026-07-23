import styles from "./BrandLogo.module.css";

type BrandLogoProps = {
  /** Intrinsic width hint for layout (CSS overrides display size). */
  width?: number;
  height?: number;
  /**
   * Force white tagline (dark surfaces). Use on the footer; header/menu
   * follow `html[data-theme]` via CSS.
   */
  onDark?: boolean;
  /** Accessible name when the parent has no aria-label. */
  alt?: string;
  className?: string;
};

/**
 * Hoocon wordmark: grey tagline on light, white tagline on dark.
 *
 * Assets: `/logo.svg` (light) and `/logo-on-dark.svg` (white slogan).
 */
export function BrandLogo({
  width = 148,
  height = 40,
  onDark = false,
  alt = "",
  className,
}: BrandLogoProps) {
  const rootClass = [styles.root, onDark ? styles.forceDark : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={rootClass}>
      <img
        className={styles.light}
        src="/logo.svg"
        alt={onDark ? "" : alt}
        width={width}
        height={height}
        decoding="async"
      />
      <img
        className={styles.dark}
        src="/logo-on-dark.svg"
        alt={onDark ? alt : ""}
        width={width}
        height={height}
        decoding="async"
      />
    </span>
  );
}
