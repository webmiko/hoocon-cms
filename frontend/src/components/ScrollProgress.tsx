import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import styles from "./ScrollProgress.module.css";

/** Light start → dark end of scroll (#ff6b6b → #8a0c0c). */
const COLOR_START = { r: 255, g: 107, b: 107 };
const COLOR_END = { r: 138, g: 12, b: 12 };

/**
 * Top-of-viewport reading progress bar.
 * Fill grows with scroll; color darkens toward the end of the page.
 */
export function ScrollProgress() {
  const location = useLocation();
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let frame = 0;
    const dims = { scrollable: 0 };

    function measure() {
      const next =
        dims.scrollable <= 0
          ? 0
          : Math.min(1, window.scrollY / dims.scrollable);
      setProgress(next);
    }

    function updateDims() {
      const doc = document.documentElement;
      dims.scrollable = doc.scrollHeight - doc.clientHeight;
      measure();
    }

    function onScroll() {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        measure();
      });
    }

    function onResize() {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        updateDims();
      });
    }

    // Cache scrollable height once, then only read cheap window.scrollY on scroll.
    updateDims();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize, { passive: true });
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
    };
  }, [location.pathname, location.search]);

  const tip = mixRgb(COLOR_START, COLOR_END, progress);
  const tipCss = `rgb(${tip.r}, ${tip.g}, ${tip.b})`;

  return (
    <div
      className={styles.track}
      role="progressbar"
      aria-label="Прогресс прокрутки страницы"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(progress * 100)}
    >
      <div
        className={styles.bar}
        style={{
          width: `${progress * 100}%`,
          background: `linear-gradient(90deg, rgb(255, 140, 140) 0%, ${tipCss} 100%)`,
          boxShadow: `0 0 10px rgba(${tip.r}, ${tip.g}, ${tip.b}, 0.4)`,
        }}
      />
    </div>
  );
}

function mixRgb(
  from: { r: number; g: number; b: number },
  to: { r: number; g: number; b: number },
  t: number,
): { r: number; g: number; b: number } {
  const clamped = Math.min(1, Math.max(0, t));
  return {
    r: Math.round(from.r + (to.r - from.r) * clamped),
    g: Math.round(from.g + (to.g - from.g) * clamped),
    b: Math.round(from.b + (to.b - from.b) * clamped),
  };
}
