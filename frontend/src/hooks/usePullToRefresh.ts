import { useCallback, useEffect, useRef, useState } from "react";

const PULL_THRESHOLD_PX = 72;
const PULL_MAX_PX = 120;
const PULL_RESISTANCE = 0.45;
const HAPTIC_ARM_MS = 12;
const HAPTIC_REFRESH_MS: number[] = [18, 40, 18];

export type PullToRefreshStatus = "idle" | "pulling" | "armed" | "refreshing";

export type UsePullToRefreshOptions = {
  onRefresh?: () => void | Promise<void>;
  disabled?: boolean;
};

export type UsePullToRefreshResult = {
  status: PullToRefreshStatus;
  pullDistance: number;
  progress: number;
};

function vibrate(pattern: number | number[]): void {
  try {
    if (typeof navigator !== "undefined" && "vibrate" in navigator) {
      navigator.vibrate(pattern);
    }
  } catch {
    // Vibration may be blocked.
  }
}

function getScrollTop(): number {
  if (typeof window === "undefined") {
    return 0;
  }
  return window.scrollY || document.documentElement.scrollTop || 0;
}

/**
 * Touch pull-to-refresh with rubber-band offset, arm threshold and haptics.
 */
export function usePullToRefresh(
  options: UsePullToRefreshOptions = {},
): UsePullToRefreshResult {
  const { onRefresh, disabled = false } = options;
  const [status, setStatus] = useState<PullToRefreshStatus>("idle");
  const [pullDistance, setPullDistance] = useState(0);

  const startYRef = useRef(0);
  const pullingRef = useRef(false);
  const armedRef = useRef(false);
  const statusRef = useRef<PullToRefreshStatus>("idle");
  const onRefreshRef = useRef(onRefresh);

  useEffect(() => {
    onRefreshRef.current = onRefresh;
  }, [onRefresh]);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  const runRefresh = useCallback(async () => {
    setStatus("refreshing");
    setPullDistance(PULL_THRESHOLD_PX * 0.65);
    vibrate(HAPTIC_REFRESH_MS);
    try {
      const handler = onRefreshRef.current;
      if (handler) {
        await handler();
      } else {
        window.location.reload();
      }
    } finally {
      setStatus("idle");
      setPullDistance(0);
      armedRef.current = false;
      pullingRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (disabled || typeof window === "undefined") {
      return;
    }

    const onTouchStart = (event: TouchEvent) => {
      if (statusRef.current === "refreshing") {
        return;
      }
      if (getScrollTop() > 0) {
        pullingRef.current = false;
        return;
      }
      const touch = event.touches[0];
      if (!touch) {
        return;
      }
      startYRef.current = touch.clientY;
      pullingRef.current = true;
      armedRef.current = false;
    };

    const onTouchMove = (event: TouchEvent) => {
      if (!pullingRef.current || statusRef.current === "refreshing") {
        return;
      }
      if (getScrollTop() > 0) {
        pullingRef.current = false;
        setPullDistance(0);
        setStatus("idle");
        return;
      }
      const touch = event.touches[0];
      if (!touch) {
        return;
      }
      const delta = touch.clientY - startYRef.current;
      if (delta <= 0) {
        setPullDistance(0);
        setStatus("idle");
        armedRef.current = false;
        return;
      }

      if (event.cancelable) {
        event.preventDefault();
      }

      const visual = Math.min(delta * PULL_RESISTANCE, PULL_MAX_PX);
      setPullDistance(visual);

      if (visual >= PULL_THRESHOLD_PX) {
        if (!armedRef.current) {
          armedRef.current = true;
          vibrate(HAPTIC_ARM_MS);
        }
        setStatus("armed");
      } else {
        armedRef.current = false;
        setStatus("pulling");
      }
    };

    const onTouchEnd = () => {
      if (!pullingRef.current) {
        return;
      }
      pullingRef.current = false;
      if (statusRef.current === "armed") {
        void runRefresh();
        return;
      }
      setStatus("idle");
      setPullDistance(0);
      armedRef.current = false;
    };

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    window.addEventListener("touchcancel", onTouchEnd, { passive: true });

    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
      window.removeEventListener("touchcancel", onTouchEnd);
    };
  }, [disabled, runRefresh]);

  return {
    status,
    pullDistance,
    progress: Math.min(pullDistance / PULL_THRESHOLD_PX, 1),
  };
}
