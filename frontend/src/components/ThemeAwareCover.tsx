import styles from "./ThemeAwareCover.module.css";

type ThemeAwareCoverProps = {
  /** Cover for light theme (and fallback / OG). Always WebP from CMS. */
  light: string;
  /** Optional cover for dark theme; falls back to light when absent. */
  dark?: string | null;
  alt?: string;
  className?: string;
  imgClassName?: string;
  loading?: "eager" | "lazy";
};

/**
 * Article/news cover that swaps light/dark assets with ``html[data-theme]``.
 *
 * Same pattern as BrandLogo: both images in DOM, CSS toggles visibility.
 */
export function ThemeAwareCover({
  light,
  dark,
  alt = "",
  className,
  imgClassName,
  loading = "lazy",
}: ThemeAwareCoverProps) {
  const hasDark = Boolean(dark);
  return (
    <span className={[styles.root, className].filter(Boolean).join(" ")}>
      <img
        className={[styles.light, imgClassName].filter(Boolean).join(" ")}
        src={light}
        alt={alt}
        loading={loading}
        decoding="async"
      />
      {hasDark ? (
        <img
          className={[styles.dark, imgClassName].filter(Boolean).join(" ")}
          src={dark!}
          alt=""
          aria-hidden
          loading={loading}
          decoding="async"
        />
      ) : null}
    </span>
  );
}
