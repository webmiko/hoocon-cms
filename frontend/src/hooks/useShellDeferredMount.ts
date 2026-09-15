import { useEffect, useState } from "react";

import {
  SUPPORT_CHAT_EVENT,
  getSupportChatState,
  subscribeSupportChat,
} from "../utils/supportChatControl";

export type ShellDeferredMountMode = "idle" | "interaction";

type UseShellDeferredMountOptions = {
  mode: ShellDeferredMountMode;
  /** Skip deferral when true (e.g. support chat opened via URL). */
  eagerWhen?: () => boolean;
  /** Mount when the support panel opens before idle (SupportWidget only). */
  watchSupportChat?: boolean;
};

function afterWindowLoad(run: () => void): void {
  if (typeof document === "undefined" || typeof window === "undefined") {
    run();
    return;
  }
  if (document.readyState === "complete") {
    run();
    return;
  }
  window.addEventListener("load", run, { once: true });
}

/** After load, mount on idle so PSI lab stays clear of heavy shell chunks. */
export function scheduleIdleMount(onReady: () => void): () => void {
  let cancelled = false;
  let idleId: number | undefined;
  let timerId: ReturnType<typeof setTimeout> | undefined;

  afterWindowLoad(() => {
    if (cancelled) {
      return;
    }
    if (typeof window.requestIdleCallback === "function") {
      idleId = window.requestIdleCallback(
        () => {
          if (!cancelled) {
            onReady();
          }
        },
        { timeout: 8000 },
      );
      return;
    }
    timerId = globalThis.setTimeout(() => {
      if (!cancelled) {
        onReady();
      }
    }, 1);
  });

  return () => {
    cancelled = true;
    if (idleId !== undefined && typeof window.cancelIdleCallback === "function") {
      window.cancelIdleCallback(idleId);
    }
    if (timerId !== undefined) {
      globalThis.clearTimeout(timerId);
    }
  };
}

/** Mount on first scroll / pointer / keyboard input — keeps dock off the TTI window. */
export function scheduleInteractionMount(onReady: () => void): () => void {
  const events: Array<keyof WindowEventMap> = [
    "pointerdown",
    "keydown",
    "touchstart",
    "scroll",
  ];
  let done = false;

  const fire = () => {
    if (done) {
      return;
    }
    done = true;
    onReady();
    for (const event of events) {
      window.removeEventListener(event, fire);
    }
  };

  for (const event of events) {
    window.addEventListener(event, fire, { passive: true });
  }

  return () => {
    done = true;
    for (const event of events) {
      window.removeEventListener(event, fire);
    }
  };
}

/**
 * Gate lazy shell widgets (support chat, compare dock, push prompt) off first paint.
 */
export function useShellDeferredMount({
  mode,
  eagerWhen,
  watchSupportChat = false,
}: UseShellDeferredMountOptions): boolean {
  const [ready, setReady] = useState(() => eagerWhen?.() ?? false);

  useEffect(() => {
    if (ready) {
      return undefined;
    }

    const mount = () => setReady(true);

    if (eagerWhen?.()) {
      mount();
      return undefined;
    }

    let cleanupSchedule: (() => void) | undefined;
    let cleanupChat: (() => void) | undefined;

    if (watchSupportChat) {
      cleanupChat = subscribeSupportChat((state) => {
        if (state.open) {
          mount();
        }
      });
      const onChatEvent = () => {
        if (getSupportChatState().open) {
          mount();
        }
      };
      window.addEventListener(SUPPORT_CHAT_EVENT, onChatEvent);
      cleanupSchedule = () => {
        cleanupChat?.();
        window.removeEventListener(SUPPORT_CHAT_EVENT, onChatEvent);
      };
    }

    const scheduleCleanup =
      mode === "idle"
        ? scheduleIdleMount(mount)
        : scheduleInteractionMount(mount);

    return () => {
      scheduleCleanup();
      cleanupSchedule?.();
    };
  }, [ready, mode, eagerWhen, watchSupportChat]);

  return ready;
}
