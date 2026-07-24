import { describe, expect, it } from "vitest";

import type { SiblingEdition } from "./skuVariantResolve";
import {
  controlPickerToHighlight,
  overlayAttributesForSibling,
  overlayCopyForSibling,
  overlayHighlightsForSibling,
} from "./skuSiblingOverlay";

const siblingB: SiblingEdition = {
  slug: "8100-bv215b",
  sku_code: "8100-BV215B",
  body: "",
  dn: "15",
  ways: "2",
  kvs: "4",
  voltage: "",
  control: "",
  aux_switch: false,
  in_stock: true,
};

const siblingDaD: SiblingEdition = {
  slug: "da8mu24-d",
  sku_code: "DA8MU24-D",
  body: "",
  dn: "",
  ways: "",
  kvs: "",
  voltage: "24",
  control: "D",
  aux_switch: false,
  in_stock: true,
};

describe("skuSiblingOverlay", () => {
  it("patches Kvs highlight and attribute from sibling", () => {
    const highlights = overlayHighlightsForSibling(
      [
        { key: "dn", name: "DN", value: "15", unit: "" },
        { key: "kvs", name: "Kvs", value: "2,5", unit: "м³/ч" },
      ],
      siblingB,
    );
    expect(highlights.find((h) => h.key === "kvs")?.value).toBe("4");

    const attrs = overlayAttributesForSibling(
      [
        { name: "DN", slug: "dn", unit: "", value: "15" },
        { name: "Kvs", slug: "kvs", unit: "м³/ч", value: "2,5" },
      ],
      siblingB,
    );
    expect(attrs.find((a) => a.slug === "kvs")?.value).toBe("4");
  });

  it("maps picker control D to 2-/3-позиционное, not the letter D", () => {
    expect(controlPickerToHighlight("D")).toBe("2-/3-позиционное");
    expect(controlPickerToHighlight("A")).toBe("Пропорциональное");

    const highlights = overlayHighlightsForSibling(
      [
        {
          key: "control",
          name: "Управление",
          value: "Пропорциональное",
          unit: "",
        },
        {
          key: "voltage",
          name: "Напряжение",
          value: "AC/DC 24 В, 50/60 Гц",
          unit: "",
        },
      ],
      siblingDaD,
    );
    expect(highlights.find((h) => h.key === "control")?.value).toBe(
      "2-/3-позиционное",
    );
    // Bare sibling voltage must not wipe Belimo wording.
    expect(highlights.find((h) => h.key === "voltage")?.value).toBe(
      "AC/DC 24 В, 50/60 Гц",
    );
  });

  it("strips Y/U when soft-nav switches from A/AS to on/off D", () => {
    const highlights = overlayHighlightsForSibling(
      [
        {
          key: "control",
          name: "Управление",
          value: "Пропорциональное",
          unit: "",
        },
        {
          key: "control_signal",
          name: "Управляющий сигнал Y",
          value: "0(2)...10 В= / 0(4)...20 мА (спецзаказ)",
          unit: "",
        },
        {
          key: "feedback_signal",
          name: "Обратная связь U",
          value: "0(2)...10 В= / 0(4)...20 мА (спецзаказ)",
          unit: "",
        },
        { key: "dn", name: "DN", value: "65", unit: "" },
      ],
      siblingDaD,
    );
    expect(highlights.map((h) => h.key)).toEqual(["control", "dn"]);
    expect(highlights.find((h) => h.key === "control")?.value).toBe(
      "2-/3-позиционное",
    );

    const attrs = overlayAttributesForSibling(
      [
        {
          name: "Управление",
          slug: "control",
          unit: "",
          value: "Пропорциональное",
        },
        {
          name: "Управляющий сигнал Y",
          slug: "control-signal",
          unit: "",
          value: "0(2)...10 В=",
        },
        {
          name: "Обратная связь U",
          slug: "feedback-signal",
          unit: "",
          value: "0(2)...10 В=",
        },
      ],
      siblingDaD,
    );
    expect(attrs.map((a) => a.slug)).toEqual(["control"]);
  });

  it("injects Y/U when soft-nav switches from D to proportional A", () => {
    const siblingA: SiblingEdition = {
      ...siblingDaD,
      slug: "da8mu24-a",
      sku_code: "DA8MU24-A",
      control: "A",
    };
    const highlights = overlayHighlightsForSibling(
      [
        {
          key: "control",
          name: "Управление",
          value: "2-/3-позиционное",
          unit: "",
        },
        { key: "dn", name: "DN", value: "65", unit: "" },
      ],
      siblingA,
    );
    expect(highlights.map((h) => h.key)).toEqual([
      "control",
      "control_signal",
      "feedback_signal",
      "dn",
    ]);
    expect(highlights.find((h) => h.key === "control")?.value).toBe(
      "Пропорциональное",
    );
    expect(highlights.find((h) => h.key === "control_signal")?.value).toContain(
      "спецзаказ",
    );
  });

  it("rewrites article and Kvs tokens in copy", () => {
    const text = overlayCopyForSibling(
      "Шаровой кран 8100-BV215A (BV215A), Kvs 2,5",
      "8100-BV215A",
      siblingB,
    );
    expect(text).toContain("8100-BV215B");
    expect(text).toContain("BV215B");
    expect(text).toMatch(/Kvs 4/);
    expect(text).not.toContain("BV215A");
  });
});
