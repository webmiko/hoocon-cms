import { describe, expect, it, vi } from "vitest";

import {
  scheduleIdleMount,
  scheduleInteractionMount,
} from "./useShellDeferredMount";

describe("useShellDeferredMount schedulers", () => {
  it("scheduleInteractionMount fires once on pointerdown", () => {
    const onReady = vi.fn();
    const cleanup = scheduleInteractionMount(onReady);

    window.dispatchEvent(new Event("scroll"));
    expect(onReady).toHaveBeenCalledTimes(1);

    window.dispatchEvent(new Event("keydown"));
    expect(onReady).toHaveBeenCalledTimes(1);

    cleanup();
  });

  it("scheduleIdleMount waits for load then idle callback", () => {
    const idle = vi.fn((cb: IdleRequestCallback) => {
      cb({ didTimeout: false, timeRemaining: () => 50 } as IdleDeadline);
      return 1;
    });
    vi.stubGlobal("requestIdleCallback", idle);

    Object.defineProperty(document, "readyState", {
      configurable: true,
      get: () => "complete",
    });

    const onReady = vi.fn();
    scheduleIdleMount(onReady);

    expect(onReady).toHaveBeenCalledTimes(1);
    expect(idle).toHaveBeenCalledTimes(1);

    vi.unstubAllGlobals();
  });
});
