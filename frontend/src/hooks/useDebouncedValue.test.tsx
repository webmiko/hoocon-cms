import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDebouncedValue } from "./useDebouncedValue";

let container: HTMLDivElement;
let root: Root;
let seen: string[] = [];

function Probe({ value }: { value: string }) {
  const debounced = useDebouncedValue(value, 250);
  seen.push(debounced);
  return null;
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  seen = [];
  container = document.createElement("div");
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  vi.useRealTimers();
});

describe("useDebouncedValue", () => {
  it("emits only the final value after typing pauses", () => {
    act(() => root.render(<Probe value="" />));
    for (const value of ["d", "da", "da2", "da24"]) {
      act(() => root.render(<Probe value={value} />));
      act(() => vi.advanceTimersByTime(100));
    }
    expect(new Set(seen)).toEqual(new Set([""]));
    act(() => vi.advanceTimersByTime(250));
    expect(seen.at(-1)).toBe("da24");
    expect(seen).not.toContain("da2");
  });
});
