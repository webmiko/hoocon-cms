/** Overlay sibling edition fields onto a loaded SKU detail for soft navigation. */

import type { SiblingEdition } from "./skuVariantResolve";

export type OverlayHighlight = {
  key: string;
  name: string;
  value: string;
  unit?: string;
};

export type OverlayAttribute = {
  name: string;
  slug: string;
  unit: string;
  value: string;
  group?: string;
  group_label?: string;
};

/** Axes whose sibling values match highlight/ТТХ display vocabulary. */
const HIGHLIGHT_FROM_SIBLING: Record<string, keyof SiblingEdition> = {
  kvs: "kvs",
  dn: "dn",
  ways: "ways",
};

const ATTR_FROM_SIBLING: Record<string, keyof SiblingEdition> = {
  kvs: "kvs",
  dn: "dn",
  ways: "ways",
};

/**
 * Picker control keys (A/AS/D/DS/DST/M) → canonical «Управление» highlight.
 *
 * Sibling ``control`` is a short edition tag for the variant picker, not the
 * Belimo-RU label shown in hero ТТХ.
 */
const CONTROL_PICKER_TO_HIGHLIGHT: Record<string, string> = {
  A: "Пропорциональное",
  AS: "Пропорциональное",
  D: "2-/3-позиционное",
  DS: "2-/3-позиционное",
  DST: "2-/3-позиционное",
  M: "Modbus RS-485",
};

/** Belimo RU Y/U rows — only for пропорциональное (A/AS); mirror backend tech_copy. */
const CONTROL_SIGNAL_Y_HIGHLIGHT: OverlayHighlight = {
  key: "control_signal",
  name: "Управляющий сигнал Y",
  value: "0(2)...10 В= / 0(4)...20 мА (спецзаказ)",
  unit: "",
};

const FEEDBACK_SIGNAL_U_HIGHLIGHT: OverlayHighlight = {
  key: "feedback_signal",
  name: "Обратная связь U",
  value: "0(2)...10 В= / 0(4)...20 мА (спецзаказ)",
  unit: "",
};

const CONTROL_SIGNAL_Y_ATTR: OverlayAttribute = {
  name: "Управляющий сигнал Y",
  slug: "control-signal",
  unit: "",
  value: CONTROL_SIGNAL_Y_HIGHLIGHT.value,
  group: "electrical",
  group_label: "Электрические параметры",
};

const FEEDBACK_SIGNAL_U_ATTR: OverlayAttribute = {
  name: "Обратная связь U",
  slug: "feedback-signal",
  unit: "",
  value: FEEDBACK_SIGNAL_U_HIGHLIGHT.value,
  group: "electrical",
  group_label: "Электрические параметры",
};

/**
 * Map a PDP picker control key to the hero «Управление» label.
 *
 * Args:
 *   pickerKey: Sibling ``control`` (``A`` / ``D`` / ``DST`` / …).
 *
 * Returns:
 *   Canonical highlight value, or empty when unknown.
 */
export function controlPickerToHighlight(pickerKey: string): string {
  return CONTROL_PICKER_TO_HIGHLIGHT[pickerKey.trim().toUpperCase()] ?? "";
}

function pickerIsProportional(pickerKey: string): boolean {
  const key = pickerKey.trim().toUpperCase();
  return key === "A" || key === "AS";
}

/**
 * Keep Y/U only for A/AS; drop for D/DS/DST/M. Soft-nav reuses the previous
 * SKU payload until the new detail loads — without this, on/off shows
 * пропорциональные сигналы (or A lacks them after leaving D).
 */
function syncModulatingSignalHighlights<T extends OverlayHighlight>(
  rows: T[],
  sibling: SiblingEdition,
): T[] {
  const picker = (sibling.control || "").trim();
  if (!picker) return rows;

  const without = rows.filter(
    (row) => row.key !== "control_signal" && row.key !== "feedback_signal",
  );
  if (!pickerIsProportional(picker)) {
    return without;
  }

  const prevY = rows.find((row) => row.key === "control_signal");
  const prevU = rows.find((row) => row.key === "feedback_signal");
  const y = (prevY ?? ({ ...CONTROL_SIGNAL_Y_HIGHLIGHT } as T)) as T;
  const u = (prevU ?? ({ ...FEEDBACK_SIGNAL_U_HIGHLIGHT } as T)) as T;
  const controlIdx = without.findIndex((row) => row.key === "control");
  if (controlIdx < 0) {
    return [...without, y, u];
  }
  return [
    ...without.slice(0, controlIdx + 1),
    y,
    u,
    ...without.slice(controlIdx + 1),
  ];
}

function syncModulatingSignalAttributes<T extends OverlayAttribute>(
  rows: T[],
  sibling: SiblingEdition,
): T[] {
  const picker = (sibling.control || "").trim();
  if (!picker) return rows;

  const without = rows.filter(
    (row) => row.slug !== "control-signal" && row.slug !== "feedback-signal",
  );
  if (!pickerIsProportional(picker)) {
    return without;
  }

  const prevY = rows.find((row) => row.slug === "control-signal");
  const prevU = rows.find((row) => row.slug === "feedback-signal");
  const y = (prevY ?? ({ ...CONTROL_SIGNAL_Y_ATTR } as T)) as T;
  const u = (prevU ?? ({ ...FEEDBACK_SIGNAL_U_ATTR } as T)) as T;
  const controlIdx = without.findIndex((row) => row.slug === "control");
  if (controlIdx < 0) {
    return [...without, y, u];
  }
  return [
    ...without.slice(0, controlIdx + 1),
    y,
    u,
    ...without.slice(controlIdx + 1),
  ];
}

/**
 * Patch hero highlights with axes from the route-selected sibling edition.
 *
 * Used while / after soft-navigating between family SKUs so Kvs / DN / ways
 * update immediately even before the full detail response arrives.
 * ``control`` is mapped from picker keys; ``voltage`` is never overlaid
 * (sibling has bare ``24``/``230``, highlights keep full Belimo wording).
 * Y/U signal rows follow пропорциональное vs on/off / Modbus.
 */
export function overlayHighlightsForSibling<T extends OverlayHighlight>(
  highlights: T[] | undefined,
  sibling: SiblingEdition | null | undefined,
): T[] {
  if (!highlights?.length || !sibling) return highlights ?? [];
  const patched = highlights.map((row) => {
    if (row.key === "control") {
      const next = controlPickerToHighlight(sibling.control);
      if (!next || next === row.value) return row;
      return { ...row, value: next };
    }
    const field = HIGHLIGHT_FROM_SIBLING[row.key];
    if (!field) return row;
    const next = String(sibling[field] ?? "").trim();
    if (!next || next === row.value) return row;
    return { ...row, value: next };
  });
  return syncModulatingSignalHighlights(patched, sibling);
}

/**
 * Patch ТТХ attribute rows (and grouped items) with sibling axis values.
 */
export function overlayAttributesForSibling<T extends OverlayAttribute>(
  attributes: T[] | undefined,
  sibling: SiblingEdition | null | undefined,
): T[] {
  if (!attributes?.length || !sibling) return attributes ?? [];
  const patched = attributes.map((row) => {
    if (row.slug === "control") {
      const next = controlPickerToHighlight(sibling.control);
      if (!next || next === row.value) return row;
      return { ...row, value: next };
    }
    const field = ATTR_FROM_SIBLING[row.slug];
    if (!field) return row;
    const next = String(sibling[field] ?? "").trim();
    if (!next || next === row.value) return row;
    return { ...row, value: next };
  });
  return syncModulatingSignalAttributes(patched, sibling);
}

/**
 * Replace article / Kvs tokens in a title or lead when the sibling changes.
 */
export function overlayCopyForSibling(
  text: string,
  currentCode: string,
  sibling: SiblingEdition | null | undefined,
): string {
  if (!text || !sibling) return text;
  let out = text;
  const nextCode = (sibling.sku_code || "").trim();
  if (nextCode && currentCode && nextCode !== currentCode) {
    out = out.split(currentCode).join(nextCode);
    // BV215A ↔ BV215B style left-side article without 8100- prefix.
    const shortCurrent = currentCode.replace(/^8100-/i, "").toUpperCase();
    const shortNext = nextCode.replace(/^8100-/i, "").toUpperCase();
    if (shortCurrent && shortNext && shortCurrent !== shortNext) {
      out = out.split(shortCurrent).join(shortNext);
      out = out.split(shortCurrent.toLowerCase()).join(shortNext.toLowerCase());
    }
  }
  if (sibling.kvs) {
    out = out.replace(/Kvs\s*[\d.,]+/gi, `Kvs ${sibling.kvs}`);
  }
  return out;
}
