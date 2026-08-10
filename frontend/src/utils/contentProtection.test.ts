import type { SyntheticEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  preventContentTheft,
  protectedContentHandlers,
  protectedMediaImgProps,
} from "./contentProtection";

describe("preventContentTheft", () => {
  it("calls preventDefault on the event", () => {
    const event = { preventDefault: vi.fn() };
    preventContentTheft(event as unknown as SyntheticEvent);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
  });
});

describe("protectedMediaImgProps", () => {
  it("disables drag and wires theft guards", () => {
    expect(protectedMediaImgProps.draggable).toBe(false);
    expect(protectedMediaImgProps.onContextMenu).toBe(preventContentTheft);
    expect(protectedMediaImgProps.onDragStart).toBe(preventContentTheft);
  });
});

describe("protectedContentHandlers", () => {
  it("blocks copy and cut", () => {
    expect(protectedContentHandlers.onCopy).toBe(preventContentTheft);
    expect(protectedContentHandlers.onCut).toBe(preventContentTheft);
  });
});
