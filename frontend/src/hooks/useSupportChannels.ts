import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { MessengerChannel } from "../components/MessengerLinks";

const MAX_ATTEMPTS = 5;
const RETRY_BASE_MS = 800;

export async function fetchSupportChannels(): Promise<MessengerChannel[]> {
  const data = await api.supportChannels();
  return data.channels ?? [];
}

type RetryOptions = {
  maxAttempts?: number;
  retryBaseMs?: number;
  sleep?: (ms: number) => Promise<void>;
  isCancelled?: () => boolean;
};

export async function loadSupportChannelsWithRetry(
  fetcher: () => Promise<MessengerChannel[]> = fetchSupportChannels,
  options: RetryOptions = {},
): Promise<MessengerChannel[]> {
  const maxAttempts = options.maxAttempts ?? MAX_ATTEMPTS;
  const retryBaseMs = options.retryBaseMs ?? RETRY_BASE_MS;
  const sleep =
    options.sleep ??
    ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  const isCancelled = options.isCancelled ?? (() => false);

  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (isCancelled()) return [];
    try {
      return await fetcher();
    } catch (error) {
      lastError = error;
      if (attempt >= maxAttempts) break;
      await sleep(retryBaseMs * attempt);
    }
  }
  throw lastError;
}

/**
 * Load enabled support messengers for footer / chat widget.
 * Retries when backend is still booting; refetches once when tab becomes visible
 * if the first load failed.
 */
export function useSupportChannels(): MessengerChannel[] {
  const [channels, setChannels] = useState<MessengerChannel[]>([]);
  const loadedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function loadWithRetry(): Promise<MessengerChannel[]> {
      const next = await loadSupportChannelsWithRetry(fetchSupportChannels, {
        isCancelled: () => cancelled,
      });
      loadedRef.current = true;
      return next;
    }

    void (async () => {
      try {
        const next = await loadWithRetry();
        if (!cancelled) setChannels(next);
      } catch {
        /* leave empty; visibility handler may retry */
      }
    })();

    function retryIfEmpty() {
      if (cancelled || loadedRef.current) return;
      void (async () => {
        try {
          const next = await loadWithRetry();
          if (!cancelled) setChannels(next);
        } catch {
          /* still unavailable */
        }
      })();
    }

    function onVisibilityChange() {
      if (document.visibilityState !== "visible") return;
      retryIfEmpty();
    }

    function onWindowFocus() {
      retryIfEmpty();
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", onWindowFocus);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("focus", onWindowFocus);
    };
  }, []);

  return channels;
}
