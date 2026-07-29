import { useEffect, useRef, useState } from "react";

import type { SKUList } from "../api/client";
import { CatalogSkuCard } from "./CatalogSkuCard";
import styles from "./NovinkiCarousel.module.css";

/** Fixed card height (matches vertical CatalogSkuCard teaser). */
const SLIDE_HEIGHT_PX = 360;

type NovinkiCarouselProps = {
  skus: SKUList[];
};

/**
 * Home «Новинки»: native CSS scroll-snap (same pattern as DirectionsCategoryGrid
 * on mobile) — one active card, translucent peeks, browser-driven slide.
 */
export function NovinkiCarousel({ skus }: NovinkiCarouselProps) {
  const n = skus.length;
  const trackRef = useRef<HTMLUListElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const root = trackRef.current;
    if (!root || n === 0) return;

    const updateActive = () => {
      const slides = Array.from(root.children) as HTMLElement[];
      if (slides.length === 0) return;
      const mid = root.scrollLeft + root.clientWidth / 2;
      let best = 0;
      let bestDist = Number.POSITIVE_INFINITY;
      slides.forEach((el, i) => {
        const center = el.offsetLeft + el.offsetWidth / 2;
        const dist = Math.abs(center - mid);
        if (dist < bestDist) {
          bestDist = dist;
          best = i;
        }
      });
      setActiveIndex(best);
    };

    let raf = 0;
    const scheduleUpdate = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        updateActive();
      });
    };

    updateActive();
    root.addEventListener("scroll", scheduleUpdate, { passive: true });
    const ro = new ResizeObserver(scheduleUpdate);
    ro.observe(root);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      root.removeEventListener("scroll", scheduleUpdate);
      ro.disconnect();
    };
  }, [n]);

  function go(delta: number) {
    const root = trackRef.current;
    if (!root || n === 0) return;
    const next = Math.max(0, Math.min(n - 1, activeIndex + delta));
    const slide = root.children[next] as HTMLElement | undefined;
    if (!slide) return;
    const left = slide.offsetLeft - (root.clientWidth - slide.offsetWidth) / 2;
    root.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
  }

  if (n === 0) return null;

  return (
    <div className={styles.carousel}>
      <div className={styles.toolbar}>
        <button
          type="button"
          className={styles.navBtn}
          aria-label="Предыдущие новинки"
          disabled={activeIndex <= 0}
          onClick={() => go(-1)}
        >
          ←
        </button>
        <button
          type="button"
          className={styles.navBtn}
          aria-label="Следующие новинки"
          disabled={activeIndex >= n - 1}
          onClick={() => go(1)}
        >
          →
        </button>
      </div>

      <ul
        ref={trackRef}
        className={styles.track}
        role="region"
        aria-roledescription="карусель"
        aria-labelledby="novinki-heading"
      >
        {skus.map((sku, index) => {
          const active = index === activeIndex;
          return (
            <li
              key={sku.slug}
              className={
                active
                  ? `${styles.slide} ${styles.slideActive}`
                  : `${styles.slide} ${styles.slidePeek}`
              }
              style={{ height: SLIDE_HEIGHT_PX }}
            >
              <CatalogSkuCard sku={sku} variant="vertical" />
            </li>
          );
        })}
      </ul>

      <p className={styles.status} aria-live="polite">
        {activeIndex + 1} из {n}
      </p>
    </div>
  );
}
