import { describe, expect, it } from "vitest";

import {
  accentCssFromWashStops,
  averageRgb,
  compactWashStops,
  edgeWashToCss,
  rgbToCss,
  sampleEdgeColorFromImageData,
  sampleEdgeWashFromImageData,
  sampleWashStopsFromImageData,
  washStopsToCss,
} from "./sampleImageEdgeColor";

describe("averageRgb", () => {
  it("returns null for empty input", () => {
    expect(averageRgb([])).toBeNull();
  });

  it("averages channels", () => {
    expect(
      averageRgb([
        { r: 0, g: 0, b: 0 },
        { r: 100, g: 50, b: 0 },
      ]),
    ).toEqual({ r: 50, g: 25, b: 0 });
  });
});

describe("rgbToCss", () => {
  it("formats rgb()", () => {
    expect(rgbToCss({ r: 12, g: 34, b: 56 })).toBe("rgb(12, 34, 56)");
  });
});

describe("accentCssFromWashStops", () => {
  it("darkens the average stop color for borders", () => {
    expect(
      accentCssFromWashStops([
        { offset: 0, color: { r: 200, g: 200, b: 200 } },
        { offset: 1, color: { r: 100, g: 100, b: 100 } },
      ]),
    ).toBe("rgb(105, 105, 105)");
  });
});

describe("washStopsToCss", () => {
  it("builds multi-stop left-to-right gradient", () => {
    expect(
      washStopsToCss([
        { offset: 0, color: { r: 163, g: 167, b: 170 } },
        { offset: 0.5, color: { r: 179, g: 175, b: 172 } },
        { offset: 1, color: { r: 252, g: 220, b: 192 } },
      ]),
    ).toBe(
      "linear-gradient(to right, rgb(163, 167, 170) 0%, rgb(179, 175, 172) 50%, rgb(252, 220, 192) 100%)",
    );
  });
});

describe("edgeWashToCss", () => {
  it("builds left-to-right gradient", () => {
    expect(
      edgeWashToCss({
        left: { r: 163, g: 167, b: 170 },
        right: { r: 249, g: 217, b: 192 },
      }),
    ).toBe(
      "linear-gradient(to right, rgb(163, 167, 170) 0%, rgb(249, 217, 192) 100%)",
    );
  });
});

describe("compactWashStops", () => {
  it("keeps plateau then ramp like DA..MU", () => {
    const grey = { r: 163, g: 167, b: 171 };
    const mid = { r: 179, g: 175, b: 172 };
    const cream = { r: 252, g: 220, b: 192 };
    const compacted = compactWashStops([
      { offset: 0, color: grey },
      { offset: 0.25, color: grey },
      { offset: 0.5, color: mid },
      { offset: 0.75, color: { r: 217, g: 199, b: 184 } },
      { offset: 1, color: cream },
    ]);
    expect(compacted.map((s) => s.offset)).toEqual([0, 0.25, 0.5, 0.75, 1]);
    expect(compacted[0]!.color).toEqual(grey);
    expect(compacted[1]!.color).toEqual(grey);
  });

  it("extends a long grey plateau to its rightmost offset", () => {
    const grey = { r: 163, g: 167, b: 171 };
    const cream = { r: 252, g: 220, b: 192 };
    const compacted = compactWashStops([
      { offset: 0, color: grey },
      { offset: 0.2, color: grey },
      { offset: 0.4, color: grey },
      { offset: 1, color: cream },
    ]);
    expect(compacted.map((s) => s.offset)).toEqual([0, 0.4, 1]);
  });
});

describe("sampleWashStopsFromImageData", () => {
  it("samples plateau then ramp like DA..MU studio", () => {
    const w = 80;
    const h = 40;
    const data = new Uint8ClampedArray(w * h * 4);
    for (let y = 0; y < h; y += 1) {
      for (let x = 0; x < w; x += 1) {
        const i = (y * w + x) * 4;
        // Flat grey 0–40%, then linear to cream (DAMU-like).
        const t = x < w * 0.4 ? 0 : (x / w - 0.4) / 0.6;
        data[i] = Math.round(163 + (252 - 163) * t);
        data[i + 1] = Math.round(167 + (220 - 167) * t);
        data[i + 2] = Math.round(171 + (192 - 171) * t);
        data[i + 3] = 255;
      }
    }
    const stops = sampleWashStopsFromImageData(data, w, h);
    expect(stops).not.toBeNull();
    expect(stops).toHaveLength(5);
    // Left plateau ≈ grey.
    expect(stops![0]!.color.r).toBeGreaterThan(150);
    expect(stops![0]!.color.r).toBeLessThan(175);
    expect(stops![1]!.color.r).toBeGreaterThan(150);
    expect(stops![1]!.color.r).toBeLessThan(175);
    // Right is warmer / brighter red channel.
    expect(stops![4]!.color.r).toBeGreaterThan(stops![0]!.color.r + 40);
  });

  it("returns null when edges are fully transparent", () => {
    const w = 40;
    const h = 40;
    const data = new Uint8ClampedArray(w * h * 4);
    expect(sampleWashStopsFromImageData(data, w, h)).toBeNull();
  });
});

describe("sampleEdgeWashFromImageData", () => {
  it("samples left and right from a horizontal gradient", () => {
    const w = 40;
    const h = 40;
    const data = new Uint8ClampedArray(w * h * 4);
    for (let y = 0; y < h; y += 1) {
      for (let x = 0; x < w; x += 1) {
        const i = (y * w + x) * 4;
        if (x < w / 2) {
          data[i] = 163;
          data[i + 1] = 167;
          data[i + 2] = 170;
        } else {
          data[i] = 249;
          data[i + 1] = 217;
          data[i + 2] = 192;
        }
        data[i + 3] = 255;
      }
    }
    expect(sampleEdgeWashFromImageData(data, w, h)).toEqual({
      left: { r: 163, g: 167, b: 170 },
      right: { r: 249, g: 217, b: 192 },
    });
  });
});

describe("sampleEdgeColorFromImageData", () => {
  it("samples opaque corner color from a solid image", () => {
    const w = 40;
    const h = 40;
    const data = new Uint8ClampedArray(w * h * 4);
    for (let i = 0; i < data.length; i += 4) {
      data[i] = 200;
      data[i + 1] = 180;
      data[i + 2] = 160;
      data[i + 3] = 255;
    }
    expect(sampleEdgeColorFromImageData(data, w, h)).toEqual({
      r: 200,
      g: 180,
      b: 160,
    });
  });

  it("ignores fully transparent pixels", () => {
    const w = 40;
    const h = 40;
    const data = new Uint8ClampedArray(w * h * 4);
    expect(sampleEdgeColorFromImageData(data, w, h)).toBeNull();
  });
});
