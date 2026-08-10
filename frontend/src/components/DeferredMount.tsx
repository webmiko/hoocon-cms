import type { CSSProperties, ReactNode } from "react";

import { useNearViewport } from "../hooks/useNearViewport";

type DeferredMountProps = {
  children: ReactNode;
  /** Shown until the block nears the viewport. */
  fallback?: ReactNode;
  rootMargin?: string;
  /** Reserve vertical space before mount to limit CLS. */
  minHeight?: CSSProperties["minHeight"];
  className?: string;
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
}: DeferredMountProps) {
  const { ref, ready } = useNearViewport({ rootMargin });
  const style =
    !ready && minHeight !== undefined
      ? ({ minHeight } satisfies CSSProperties)
      : undefined;

  return (
    <div ref={ref} className={className} style={style}>
      {ready ? children : fallback}
    </div>
  );
}
