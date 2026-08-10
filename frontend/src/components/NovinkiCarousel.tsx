import { useEffect, useRef, useState } from "react";

import type { SKUList } from "../api/client";
import { CatalogSkuCard } from "./CatalogSkuCard";
import styles from "./NovinkiCarousel.module.css";

/** Fixed card height (matches vertical CatalogSkuCard teaser). */
const SLIDE_HEIGHT_PX = 360;
/** Slop so sub-pixel scroll/snap still counts as fully in view. */
const FULL_VIEW_EPS_PX = 2;

type NovinkiCarouselProps = {
  skus: SKUList[];
};

/**
 * Home «Новинки»: native CSS scroll-snap — fully visible cards stay opaque;
 * edge peeks dim. Center card lifts/scales slightly on wide layouts.
 */
export function NovinkiCarousel({ skus }: NovinkiCarouselProps) {
  const n = skus.length;
  const trackRef = useRef<HTMLUListElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [opaque, setOpaque] = useState<ReadonlySet<number>>(() => new Set([0]));

  useEffect(() => {
    const root = trackRef.current;
    if (!root || n === 0) return;

    const updateActive = () => {
      const slides = Array.from(root.children) as HTMLElement[];
      if (slides.length === 0) return;

      const rootRect = root.getBoundingClientRect();
      const midX = rootRect.left + rootRect.width / 2;
      const full = new Set<number>();
      let best = 0;
      let bestDist = Number.POSITIVE_INFINITY;

      slides.forEach((el, i) => {
        const rect = el.getBoundingClientRect();
        const inFull =
          rect.left >= rootRect.left - FULL_VIEW_EPS_PX &&
          rect.right <= rootRect.right + FULL_VIEW_EPS_PX;
        if (inFull) {
          full.add(i);
        }
        const center = rect.left + rect.width / 2;
        const dist = Math.abs(center - midX);
        if (dist < bestDist) {
          bestDist = dist;
          best = i;
        }
      });

      // Fallback: if snap padding leaves none "full", keep the center card opaque.
      if (full.size === 0) {
        full.add(best);
      }

      setActiveIndex(best);
      setOpaque(full);
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
    <div
      className={styles.carousel}
      role="region"
      aria-roledescription="карусель"
      aria-labelledby="novinki-heading"
    >
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

      <ul ref={trackRef} className={styles.track} role="list">
        {skus.map((sku, index) => {
          const isOpaque = opaque.has(index);
          const isCenter = index === activeIndex;
          const className = [
            styles.slide,
            isOpaque ? styles.slideFocus : styles.slidePeek,
            isCenter ? styles.slideCenter : "",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <li
              key={sku.slug}
              className={className}
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
