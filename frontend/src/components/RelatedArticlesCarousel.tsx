import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import styles from "./RelatedArticlesCarousel.module.css";

const LOOP_COPIES = 3;
const AUTOPLAY_MS = 5200;
const TRANSITION_MS = 420;
const GAP_PX = 16;
/** Peek of neighboring cards on each side (px). */
const PEEK_PX = 48;

export type RelatedContentItem = {
  slug: string;
  title: string;
  cover?: string | null;
};

interface RelatedArticlesCarouselProps {
  articles: RelatedContentItem[];
  /** Link prefix, e.g. ``/statyi`` or ``/novosti``. */
  pathPrefix?: string;
  /** Accessible label for prev/next (default: статьи). */
  navLabel?: string;
}

/**
 * Full-width related carousel: opaque center cards, translucent edge peeks.
 * Visible card count follows viewport width. Infinite loop + reduced-motion.
 */
export function RelatedArticlesCarousel({
  articles,
  pathPrefix = "/statyi",
  navLabel = "статьи",
}: RelatedArticlesCarouselProps) {
  const n = articles.length;
  const basePath = pathPrefix.replace(/\/$/, "");
  const viewportRef = useRef<HTMLDivElement>(null);
  const jumpTimer = useRef<number | null>(null);
  const dragX = useRef<number | null>(null);

  const [perPage, setPerPage] = useState(1);
  const [viewportW, setViewportW] = useState(0);
  const [index, setIndex] = useState(n);
  const [animate, setAnimate] = useState(false);
  const [paused, setPaused] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);

  const trackItems =
    n > 0 ? Array.from({ length: LOOP_COPIES }, () => articles).flat() : [];
  const middleStart = n;
  const resetKey = `${middleStart}-${n}-${perPage}`;
  const [syncedResetKey, setSyncedResetKey] = useState(resetKey);

  // Realign loop window when item count / page size changes.
  if (syncedResetKey !== resetKey) {
    setSyncedResetKey(resetKey);
    setAnimate(false);
    setIndex(middleStart);
  }

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduceMotion(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;

    const measure = () => {
      const w = el.clientWidth;
      setViewportW(w);
      // Fit as many cards as width allows (~240px min), keep room for peeks.
      const usable = Math.max(0, w - PEEK_PX * 2);
      const byWidth = Math.floor((usable + GAP_PX) / (240 + GAP_PX));
      const next = Math.max(1, Math.min(4, byWidth, Math.max(1, n)));
      setPerPage(next);
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [n]);

  const slideW =
    viewportW > 0
      ? (viewportW - PEEK_PX * 2 - (perPage - 1) * GAP_PX) / perPage
      : 240;
  const stride = slideW + GAP_PX;

  const go = useCallback(
    (delta: number) => {
      if (n === 0) return;
      setAnimate(true);
      setIndex((prev) => prev + delta);
    },
    [n],
  );

  useEffect(() => {
    if (n === 0 || !animate) return;
    if (index >= middleStart && index < middleStart + n) return;

    if (jumpTimer.current !== null) {
      window.clearTimeout(jumpTimer.current);
    }
    jumpTimer.current = window.setTimeout(() => {
      setAnimate(false);
      setIndex(((index % n) + n) % n + middleStart);
    }, TRANSITION_MS);

    return () => {
      if (jumpTimer.current !== null) {
        window.clearTimeout(jumpTimer.current);
      }
    };
  }, [animate, index, middleStart, n]);

  useEffect(() => {
    if (reduceMotion || paused || n < 2) return;
    const id = window.setInterval(() => go(1), AUTOPLAY_MS);
    return () => window.clearInterval(id);
  }, [go, n, paused, reduceMotion]);

  function onPointerDown(event: React.PointerEvent) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    dragX.current = event.clientX;
    setPaused(true);
  }

  function onPointerUp(event: React.PointerEvent) {
    if (dragX.current === null) return;
    const dx = event.clientX - dragX.current;
    dragX.current = null;
    if (Math.abs(dx) > 40) {
      go(dx < 0 ? 1 : -1);
    }
    setPaused(false);
  }

  function onPointerCancel() {
    dragX.current = null;
    setPaused(false);
  }

  if (n === 0) return null;

  const logical = ((index % n) + n) % n;
  // Opaque window: [index, index + perPage). Edge peeks: neighbors outside.
  const opaqueStart = index;
  const opaqueEnd = index + perPage;

  return (
    <div
      className={styles.carousel}
      role="region"
      aria-roledescription="карусель"
      aria-labelledby="related-heading"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) {
          setPaused(false);
        }
      }}
    >
      <div className={styles.toolbar}>
        <button
          type="button"
          className={styles.navBtn}
          aria-label={`Предыдущие ${navLabel}`}
          onClick={() => go(-1)}
        >
          ←
        </button>
        <button
          type="button"
          className={styles.navBtn}
          aria-label={`Следующие ${navLabel}`}
          onClick={() => go(1)}
        >
          →
        </button>
      </div>

      <div
        ref={viewportRef}
        className={styles.viewport}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
      >
        <ul
          className={styles.track}
          style={{
            gap: GAP_PX,
            transform: `translateX(${PEEK_PX - index * stride}px)`,
            transition:
              animate && !reduceMotion
                ? `transform ${TRANSITION_MS}ms var(--ease-out, ease)`
                : "none",
          }}
        >
          {trackItems.map((article, i) => {
            const inWindow = i >= opaqueStart && i < opaqueEnd;
            const isPeek = i === opaqueStart - 1 || i === opaqueEnd;
            const dimmed = !inWindow;
            return (
              <li
                key={`${article.slug}-${i}`}
                className={
                  dimmed
                    ? `${styles.slide} ${styles.slidePeek}`
                    : styles.slide
                }
                style={{ width: slideW, flex: `0 0 ${slideW}px` }}
                aria-hidden={!inWindow}
                data-peek={isPeek ? "true" : undefined}
              >
                <Link
                  to={`${basePath}/${article.slug}/`}
                  className={styles.card}
                  tabIndex={inWindow ? 0 : -1}
                >
                  {article.cover ? (
                    <img
                      className={styles.cover}
                      src={article.cover}
                      alt=""
                      loading="lazy"
                    />
                  ) : (
                    <div className={styles.coverPh} aria-hidden />
                  )}
                  <span className={styles.cardTitle}>{article.title}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>

      <p className={styles.status} aria-live="polite">
        {logical + 1} из {n}
      </p>
    </div>
  );
}
