import { describe, expect, it } from "vitest";

import {
  contentFillFromImageData,
  normalizePhotoScale,
  parseMomentNm,
  photoScaleFromHighlights,
  productPhotoScale,
} from "./productPhotoScale";

describe("parseMomentNm", () => {
  it("parses Russian and bare numbers", () => {
    expect(parseMomentNm("5 Нм")).toBe(5);
    expect(parseMomentNm("40")).toBe(40);
    expect(parseMomentNm("7,5 Nm")).toBe(7.5);
  });

  it("returns null for empty / non-torque", () => {
    expect(parseMomentNm("")).toBeNull();
    expect(parseMomentNm("AC/DC 24 В")).toBeNull();
  });
});

describe("productPhotoScale", () => {
  it("maps linearly from 75% (tiny) to 100% (ref max)", () => {
    expect(productPhotoScale(40)).toBe(1);
    expect(productPhotoScale(20)).toBeCloseTo(0.875, 3);
    expect(productPhotoScale(10)).toBeCloseTo(0.8125, 3);
    expect(productPhotoScale(5)).toBeCloseTo(0.78125, 3);
  });

  it("approaches the 75% floor as torque → 0", () => {
    expect(productPhotoScale(0.001)).toBeCloseTo(0.75, 3);
  });
});

describe("photoScaleFromHighlights", () => {
  it("reads moment highlight", () => {
    expect(
      photoScaleFromHighlights([
        { key: "voltage", value: "24 В" },
        { key: "moment", value: "10 Нм" },
      ]),
    ).toBeCloseTo(productPhotoScale(10), 5);
  });

  it("defaults to 1 without moment", () => {
    expect(photoScaleFromHighlights([{ key: "dn", value: "40" }])).toBe(1);
    expect(photoScaleFromHighlights(undefined)).toBe(1);
  });
});

describe("contentFillFromImageData", () => {
  it("returns ~1 for a full opaque non-white bitmap", () => {
    const w = 4;
    const h = 4;
    const data = new Uint8ClampedArray(w * h * 4);
    for (let i = 0; i < data.length; i += 4) {
      data[i] = 40;
      data[i + 1] = 40;
      data[i + 2] = 40;
      data[i + 3] = 255;
    }
    expect(contentFillFromImageData(data, w, h)).toBeCloseTo(1, 2);
  });

  it("ignores transparent margins", () => {
    const w = 4;
    const h = 4;
    const data = new Uint8ClampedArray(w * h * 4);
    for (const [x, y] of [
      [1, 1],
      [2, 1],
      [1, 2],
      [2, 2],
    ] as const) {
      const i = (y * w + x) * 4;
      data[i] = 30;
      data[i + 1] = 30;
      data[i + 2] = 30;
      data[i + 3] = 255;
    }
    expect(contentFillFromImageData(data, w, h)).toBeCloseTo(0.5, 2);
  });
});

describe("normalizePhotoScale", () => {
  it("boosts sparse crops so visual size matches torque target", () => {
    const torque = productPhotoScale(10);
    const sparse = normalizePhotoScale(torque, 0.54);
    const tight = normalizePhotoScale(torque, 0.79);
    expect(sparse).toBeGreaterThan(tight);
    expect(sparse * 0.54).toBeCloseTo(torque, 1);
    expect(tight * 0.79).toBeCloseTo(torque, 1);
  });
});
