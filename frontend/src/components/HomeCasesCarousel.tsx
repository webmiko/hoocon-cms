import { useEffect, useRef, useState } from "react";

import styles from "./HomeCasesCarousel.module.css";

/** When the cases band is this wide or narrower — snap carousel (Novinki-style). */
const CAROUSEL_MAX_PX = 1100;

export type HomeCaseProject = {
  name: string;
  lead: string;
  image: string;
  width: number;
  height: number;
};

type HomeCasesCarouselProps = {
  projects: readonly HomeCaseProject[];
};

/**
 * Home «На объектах»: 3-up grid when wide; CSS scroll-snap carousel when the
 * band is ≤1100px (card count / peeks follow width like NovinkiCarousel).
 */
export function HomeCasesCarousel({ projects }: HomeCasesCarouselProps) {
  const n = projects.length;
  const rootRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLUListElement>(null);
  const [carousel, setCarousel] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const sync = () => setCarousel(el.clientWidth <= CAROUSEL_MAX_PX);
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const root = trackRef.current;
    if (!root || !carousel || n === 0) return;

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
  }, [carousel, n]);

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
    <div ref={rootRef} className={styles.root}>
      {carousel ? (
        <div className={styles.toolbar}>
          <button
            type="button"
            className={styles.navBtn}
            aria-label="Предыдущий объект"
            disabled={activeIndex <= 0}
            onClick={() => go(-1)}
          >
            ←
          </button>
          <button
            type="button"
            className={styles.navBtn}
            aria-label="Следующий объект"
            disabled={activeIndex >= n - 1}
            onClick={() => go(1)}
          >
            →
          </button>
        </div>
      ) : null}

      <ul
        ref={trackRef}
        className={carousel ? styles.track : styles.grid}
        role={carousel ? "region" : undefined}
        aria-roledescription={carousel ? "карусель" : undefined}
        aria-labelledby="cases-heading"
      >
        {projects.map((project, index) => {
          const active = !carousel || index === activeIndex;
          return (
            <li
              key={project.name}
              className={
                carousel
                  ? active
                    ? `${styles.slide} ${styles.slideActive}`
                    : `${styles.slide} ${styles.slidePeek}`
                  : styles.slide
              }
            >
              <article className={styles.caseItem}>
                <img
                  className={styles.caseImg}
                  src={project.image}
                  alt=""
                  width={project.width}
                  height={project.height}
                  loading="lazy"
                  decoding="async"
                />
                <div className={styles.caseCaption}>
                  <h3 className={styles.caseTitle}>{project.name}</h3>
                  <p className={styles.caseLead}>{project.lead}</p>
                </div>
              </article>
            </li>
          );
        })}
      </ul>

      {carousel ? (
        <p className={styles.status} aria-live="polite">
          {activeIndex + 1} из {n}
        </p>
      ) : null}
    </div>
  );
}
