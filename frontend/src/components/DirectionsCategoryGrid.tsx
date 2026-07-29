import { useEffect, useRef, useState, type ComponentType } from "react";
import { Link } from "react-router-dom";

import { softBreak } from "../utils/softBreak";
import { catalogCategoryPath } from "../utils/catalogPaths";
import styles from "../pages/HomePage.module.css";

const CAROUSEL_MQ = "(max-width: 920px)";

export type DirectionCategory = {
  slug: string;
  name: string;
  description?: string | null;
  image?: { image?: string | null } | null;
};

type DirectionsCategoryGridProps = {
  categories: DirectionCategory[];
  categoryLead: (description: string) => string;
  DirectionCardImage: ComponentType<{
    apiSrc: string | null | undefined;
    className: string;
    placeholderClassName: string;
  }>;
};

/**
 * Category pillars: CSS grid on wide screens; snap carousel ≤920px
 * with one active card and translucent side peeks.
 */
export function DirectionsCategoryGrid({
  categories,
  categoryLead,
  DirectionCardImage,
}: DirectionsCategoryGridProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [carousel, setCarousel] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [trackWidth, setTrackWidth] = useState(0);

  useEffect(() => {
    const mq = window.matchMedia(CAROUSEL_MQ);
    const sync = () => setCarousel(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    const root = trackRef.current;
    if (!root || !carousel || categories.length === 0) {
      return;
    }

    const updateActive = () => {
      const slides = Array.from(root.children) as HTMLElement[];
      if (slides.length === 0) return;
      setTrackWidth(root.clientWidth);
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
  }, [carousel, categories.length]);

  const focusCount = carousel && trackWidth >= 840 ? 2 : 1;
  const activeWindowStart =
    focusCount === 1
      ? activeIndex
      : Math.min(activeIndex, Math.max(0, categories.length - focusCount));

  return (
    <div
      ref={trackRef}
      className={styles.directionGrid}
      role={carousel ? "region" : undefined}
      aria-roledescription={carousel ? "карусель" : undefined}
      aria-label={carousel ? "Направления продукции" : undefined}
    >
      {categories.map((cat, index) => {
        const lead = categoryLead(cat.description ?? "");
        const active =
          !carousel ||
          (index >= activeWindowStart && index < activeWindowStart + focusCount);
        return (
          <Link
            key={cat.slug}
            to={catalogCategoryPath(cat.slug)}
            className={
              active
                ? `${styles.directionBlock} ${styles.directionBlockActive}`
                : `${styles.directionBlock} ${styles.directionBlockPeek}`
            }
            style={{ animationDelay: `${0.06 + index * 0.05}s` }}
            tabIndex={carousel && !active ? -1 : undefined}
            aria-hidden={carousel && !active ? true : undefined}
          >
            <span className={styles.directionMedia}>
              <DirectionCardImage
                apiSrc={cat.image?.image}
                className={styles.directionImage}
                placeholderClassName={styles.directionImagePlaceholder}
              />
            </span>
            <span className={styles.directionBody}>
              <span className={styles.directionName}>
                {softBreak(cat.name)}
              </span>
              {lead ? (
                <span className={styles.directionDesc}>{lead}</span>
              ) : null}
              <span className={styles.directionMore}>В каталог →</span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}
