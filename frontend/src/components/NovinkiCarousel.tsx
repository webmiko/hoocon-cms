import { useCallback, useEffect, useRef, useState } from "react";

import type { SKUList } from "../api/client";
import { CatalogSkuCard } from "./CatalogSkuCard";
import styles from "./NovinkiCarousel.module.css";

const LOOP_COPIES = 3;
const AUTOPLAY_MS = 5600;
const TRANSITION_MS = 420;
const GAP_PX = 16;
/** Peek of neighboring cards on each side (px). */
const PEEK_PX = 40;
/** Min width for a catalog card slide (horizontal layout needs room). */
const MIN_SLIDE_PX = 280;

type NovinkiCarouselProps = {
  skus: SKUList[];
};

/**
 * Home «Новинки» carousel: CatalogSkuCard slides, peeks, autoplay, reduced-motion.
 * Pattern aligned with RelatedArticlesCarousel.
 */
export function NovinkiCarousel({ skus }: NovinkiCarouselProps) {
  const n = skus.length;
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
    n > 0 ? Array.from({ length: LOOP_COPIES }, () => skus).flat() : [];
  const middleStart = n;
  const resetKey = `${middleStart}-${n}-${perPage}`;
  const [syncedResetKey, setSyncedResetKey] = useState(resetKey);

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
      const usable = Math.max(0, w - PEEK_PX * 2);
      const byWidth = Math.floor((usable + GAP_PX) / (MIN_SLIDE_PX + GAP_PX));
      const next = Math.max(1, Math.min(3, byWidth, Math.max(1, n)));
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
      : MIN_SLIDE_PX;
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
  const opaqueStart = index;
  const opaqueEnd = index + perPage;

  return (
    <div
      className={styles.carousel}
      role="region"
      aria-roledescription="карусель"
      aria-labelledby="novinki-heading"
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
          aria-label="Предыдущие новинки"
          onClick={() => go(-1)}
        >
          ←
        </button>
        <button
          type="button"
          className={styles.navBtn}
          aria-label="Следующие новинки"
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
          {trackItems.map((sku, i) => {
            const inWindow = i >= opaqueStart && i < opaqueEnd;
            const isPeek = i === opaqueStart - 1 || i === opaqueEnd;
            const dimmed = !inWindow;
            return (
              <li
                key={`${sku.slug}-${i}`}
                className={
                  dimmed
                    ? `${styles.slide} ${styles.slidePeek}`
                    : styles.slide
                }
                style={{ width: slideW, flex: `0 0 ${slideW}px` }}
                aria-hidden={!inWindow}
                inert={!inWindow ? true : undefined}
                data-peek={isPeek ? "true" : undefined}
              >
                <CatalogSkuCard sku={sku} omitDomId />
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
