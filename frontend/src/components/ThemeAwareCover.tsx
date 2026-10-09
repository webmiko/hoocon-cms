import { useContext } from "react";

import { ThemeContext } from "../theme/ThemeContext";
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

function documentIsDark(): boolean {
  return typeof document !== "undefined" && document.documentElement.dataset.theme === "dark";
}

/**
 * Article/news cover for the resolved light/dark theme.
 *
 * One ``<img>`` whose src follows the theme: two hidden-by-CSS images both
 * downloaded eagerly and doubled the LCP bytes. Page CSS gives the img an
 * aspect-ratio, so swapping src on theme change does not shift layout.
 */
export function ThemeAwareCover({
  light,
  dark,
  alt = "",
  className,
  imgClassName,
  loading = "lazy",
}: ThemeAwareCoverProps) {
  const theme = useContext(ThemeContext);
  const isDark = theme ? theme.resolved === "dark" : documentIsDark();
  const src = isDark && dark ? dark : light;
  return (
    <span className={[styles.root, className].filter(Boolean).join(" ")}>
      <img
        className={imgClassName}
        src={src}
        alt={alt}
        loading={loading}
        fetchPriority={loading === "eager" ? "high" : undefined}
        decoding="async"
      />
    </span>
  );
}
