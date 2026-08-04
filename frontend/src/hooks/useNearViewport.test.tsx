import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";

import { useNearViewport } from "../hooks/useNearViewport";

function Probe({ onReady }: { onReady: (ready: boolean) => void }) {
  const { ref, ready } = useNearViewport({ rootMargin: "0px" });
  onReady(ready);
  return <div ref={ref} data-testid="probe" />;
}

describe("useNearViewport", () => {
  let observe: ReturnType<typeof vi.fn>;
  let disconnect: ReturnType<typeof vi.fn>;
  let trigger: ((entries: IntersectionObserverEntry[]) => void) | null;

  beforeEach(() => {
    observe = vi.fn();
    disconnect = vi.fn();
    trigger = null;
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(cb: (entries: IntersectionObserverEntry[]) => void) {
          trigger = cb;
        }
        observe = observe;
        disconnect = disconnect;
        unobserve = vi.fn();
        takeRecords = () => [];
        root = null;
        rootMargin = "";
        thresholds = [];
      },
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("becomes ready after intersection and disconnects when once", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const seen: boolean[] = [];

    await act(async () => {
      root.render(<Probe onReady={(r) => seen.push(r)} />);
    });
    expect(seen.at(-1)).toBe(false);
    expect(observe).toHaveBeenCalled();

    await act(async () => {
      trigger?.([{ isIntersecting: true } as IntersectionObserverEntry]);
    });
    expect(seen.at(-1)).toBe(true);
    expect(disconnect).toHaveBeenCalled();

    await act(async () => {
      root.unmount();
    });
    host.remove();
  });
});
