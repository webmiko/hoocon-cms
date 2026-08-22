import type { CSSProperties, ReactNode } from "react";

import { useDeferredMount } from "../hooks/useDeferredMount";

type DeferredMountProps = {
  children: ReactNode;
  /** Shown until the block nears the viewport. */
  fallback?: ReactNode;
  rootMargin?: string;
  /** Reserve vertical space before mount to limit CLS. */
  minHeight?: CSSProperties["minHeight"];
  className?: string;
  /** Anchor target while children are not mounted (e.g. home ``#podbor``). */
  id?: string;
  /** Require scroll before mount (PSI lab runs stay at scrollY 0). */
  requireScrollPx?: number;
  /** Mount when ``location.hash`` matches (without ``#``). */
  hashIds?: readonly string[];
};

/**
 * Mount ``children`` only when the placeholder nears the viewport.
 *
 * Use for below-fold home sections so JS/API/images stay off the first paint.
 */
export function DeferredMount({
  children,
  fallback = null,
  rootMargin = "240px 0px",
  minHeight,
  className,
  id,
  requireScrollPx,
  hashIds,
}: DeferredMountProps) {
  const { ref, ready } = useDeferredMount({
    rootMargin,
    requireScrollPx,
    hashIds,
  });
  const style =
    !ready && minHeight !== undefined
      ? ({ minHeight } satisfies CSSProperties)
      : undefined;

  return (
    <div ref={ref} id={id} className={className} style={style}>
      {ready ? children : fallback}
    </div>
  );
}
