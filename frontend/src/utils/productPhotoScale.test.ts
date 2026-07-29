import { describe, expect, it } from "vitest";

import {
  contentFillFromImageData,
  isHvCanvasMediaSku,
  normalizePhotoScale,
  parseDn,
  parseMomentNm,
  photoScaleFromHighlights,
  photoScalePlanFromHighlights,
  PHOTO_SCALE_CSS_MAX,
  PHOTO_SCALE_REF_DN,
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

describe("parseDn", () => {
  it("parses bare and DN-prefixed values", () => {
    expect(parseDn("20")).toBe(20);
    expect(parseDn("DN50")).toBe(50);
    expect(parseDn("dn 15")).toBe(15);
  });

  it("returns null for empty / non-DN", () => {
    expect(parseDn("")).toBeNull();
    expect(parseDn("G1/2")).toBeNull();
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

  it("maps valve DN like torque (DN50 = full frame)", () => {
    expect(productPhotoScale(50, { refMaxNm: PHOTO_SCALE_REF_DN })).toBe(1);
    expect(productPhotoScale(20, { refMaxNm: PHOTO_SCALE_REF_DN })).toBeCloseTo(
      0.85,
      3,
    );
    expect(productPhotoScale(15, { refMaxNm: PHOTO_SCALE_REF_DN })).toBeCloseTo(
      0.825,
      3,
    );
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

  it("prefers moment over DN", () => {
    expect(
      photoScaleFromHighlights([
        { key: "dn", value: "50" },
        { key: "moment", value: "5 Нм" },
      ]),
    ).toBeCloseTo(productPhotoScale(5), 5);
  });

  it("maps DN when moment is absent (brass valve heroes)", () => {
    // Relative DN size is baked into pack cutouts — FE keeps target 1.
    expect(photoScaleFromHighlights([{ key: "dn", value: "20" }])).toBe(1);
  });

  it("defaults to 1 without moment or DN", () => {
    expect(photoScaleFromHighlights([{ key: "ways", value: "2-ходовый" }])).toBe(
      1,
    );
    expect(photoScaleFromHighlights(undefined)).toBe(1);
  });
});

describe("isHvCanvasMediaSku", () => {
  it("matches HVA/HVD air and smoke F editions", () => {
    expect(isHvCanvasMediaSku("HVA24-10Q")).toBe(true);
    expect(isHvCanvasMediaSku("HVD230S-40QX")).toBe(true);
    expect(isHvCanvasMediaSku("hva24s-5")).toBe(true);
    expect(isHvCanvasMediaSku("HVD24S-5F")).toBe(true);
    expect(isHvCanvasMediaSku("HVD230ST-3F")).toBe(true);
  });

  it("skips non-HV", () => {
    expect(isHvCanvasMediaSku("DA8MU24-D")).toBe(false);
    expect(isHvCanvasMediaSku("8100-BV215A")).toBe(false);
  });
});

describe("photoScalePlanFromHighlights", () => {
  it("allows actuator boost above 1", () => {
    const plan = photoScalePlanFromHighlights([{ key: "moment", value: "10 Нм" }]);
    expect(plan.maxCssScale).toBe(PHOTO_SCALE_CSS_MAX);
  });

  it("caps valve DN heroes at CSS scale 1 with target 1", () => {
    const plan = photoScalePlanFromHighlights([{ key: "dn", value: "32" }]);
    expect(plan.target).toBe(1);
    expect(plan.maxCssScale).toBe(1);
  });

  it("caps baked HVA/HVD heroes at CSS scale 1", () => {
    const plan = photoScalePlanFromHighlights(
      [{ key: "moment", value: "5 Нм" }],
      "HVA24-5",
    );
    expect(plan.target).toBe(1);
    expect(plan.maxCssScale).toBe(1);
  });

  it("keeps DA/SA moment scale when sku is not HV canvas", () => {
    const plan = photoScalePlanFromHighlights(
      [{ key: "moment", value: "10 Нм" }],
      "DA10MU24-DS",
    );
    expect(plan.target).toBeCloseTo(productPhotoScale(10), 5);
    expect(plan.maxCssScale).toBe(PHOTO_SCALE_CSS_MAX);
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

  it("does not enlarge valve DN crops past the media cell", () => {
    const target = productPhotoScale(32, { refMaxNm: PHOTO_SCALE_REF_DN });
    expect(normalizePhotoScale(target, 0.77, 1)).toBe(1);
    expect(normalizePhotoScale(target, 0.95, 1)).toBeCloseTo(target / 0.95, 3);
  });
});
