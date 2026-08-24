import type { CatalogFacet } from "../../api/client";
import type {
  QuizAuxSwitch,
  QuizControl,
  QuizDn,
  QuizKvs,
  QuizTempSensor,
  QuizVoltage,
  QuizWays,
} from "./quizEngine";
import { parseAreaM2, parseMomentNm } from "./quizMomentEstimate";

export { parseAreaM2, parseMomentNm } from "./quizMomentEstimate";

export function matchVoltageFacet(
  values: readonly string[],
  choice: Exclude<QuizVoltage, "skip">,
): string | null {
  for (const value of values) {
    const raw = value.trim();
    if (!raw) continue;
    if (choice === "24") {
      if (/\b24\b/.test(raw) && !/230|240|100/.test(raw)) {
        return value;
      }
    }
    if (choice === "230") {
      if (/230|240|100\s*[.…\-−–—]+\s*240/.test(raw)) {
        return value;
      }
    }
  }
  return null;
}

export function matchControlFacet(
  values: readonly string[],
  choice: Exclude<QuizControl, "skip">,
): string | null {
  let onOffLabel: string | null = null;
  let floatingLabel: string | null = null;
  let modulatingLabel: string | null = null;

  for (const value of values) {
    const raw = value.trim();
    if (!raw) continue;
    if (/открыто\s*\/\s*закрыто|вкл|on\/off/i.test(raw)) {
      onOffLabel ??= value;
    }
    if (/2\s*[-–—]?\s*\/\s*3|позицион/i.test(raw)) {
      floatingLabel ??= value;
    }
    if (/пропорциональн|модулир|плавн|0\s*[(.…\-−–—]?\s*10/i.test(raw)) {
      modulatingLabel ??= value;
    }
  }

  if (choice === "modulating") {
    return modulatingLabel;
  }

  // Discrete on/off may be stored as two canon chips — OR them so DA…D and
  // HVD air are not dropped when the user asks for «открыть / закрыть».
  const discrete = [floatingLabel, onOffLabel].filter(
    (label): label is string => Boolean(label),
  );
  if (discrete.length === 0) {
    return null;
  }
  return [...new Set(discrete)].join(",");
}

export function matchMomentNmFacet(
  values: readonly string[],
  targetNm: number,
): string | null {
  const parsed = values
    .map((value) => ({ value, nm: parseMomentNm(value) }))
    .filter((row): row is { value: string; nm: number } => row.nm !== null);

  const exact = parsed.find((row) => row.nm === targetNm);
  if (exact) {
    return exact.value;
  }

  parsed.sort((a, b) => a.nm - b.nm);
  return parsed.find((row) => row.nm >= targetNm)?.value ?? parsed.at(-1)?.value ?? null;
}

/** Smallest catalog ``до X м²`` label that covers the moment tier. */
export function matchAreaForMomentNmFacet(
  values: readonly string[],
  targetNm: number,
): string | null {
  const parsed = values
    .map((value) => ({ value, m2: parseAreaM2(value) }))
    .filter((row): row is { value: string; m2: number } => row.m2 !== null)
    .sort((a, b) => a.m2 - b.m2);

  for (const row of parsed) {
    const implied = momentForAreaCapM2(row.m2);
    if (implied !== null && implied >= targetNm) {
      return row.value;
    }
  }

  return parsed.at(-1)?.value ?? null;
}

/** Catalog area cap (m²) → typical moment step from Hoocon ladder. */
function momentForAreaCapM2(capM2: number): number | null {
  const ladder: Array<[number, number]> = [
    [0.2, 2],
    [0.4, 4],
    [0.5, 5],
    [0.6, 6],
    [0.8, 8],
    [1.0, 10],
    [1.6, 16],
    [2.0, 20],
    [2.4, 24],
    [3.2, 32],
    [4.0, 40],
  ];
  for (const [area, nm] of ladder) {
    if (capM2 <= area + 0.001) {
      return nm;
    }
  }
  return 40;
}

export function matchAuxSwitchFacet(
  values: readonly string[],
  choice: Exclude<QuizAuxSwitch, "skip">,
): string | null {
  if (choice === "no") {
    for (const value of values) {
      if (/^нет$/i.test(value.trim())) {
        return value;
      }
    }
    return null;
  }

  for (const value of values) {
    if (/SPDT-2/i.test(value.trim())) {
      return value;
    }
  }
  for (const value of values) {
    if (/SPDT-1/i.test(value.trim())) {
      return value;
    }
  }
  return null;
}

export function matchTempSensorFacet(
  values: readonly string[],
  choice: Exclude<QuizTempSensor, "skip">,
): string | null {
  for (const value of values) {
    const raw = value.trim();
    if (choice === "yes" && /SAF72/i.test(raw)) {
      return value;
    }
    if (choice === "no" && /^нет$/i.test(raw)) {
      return value;
    }
  }
  return null;
}

export function matchDnFacet(
  values: readonly string[],
  dn: Exclude<QuizDn, "skip">,
): string | null {
  const needle = dn.trim();
  for (const value of values) {
    const raw = value.trim();
    if (new RegExp(`\\bDN\\s*0*${needle}\\b`, "i").test(raw)) {
      return value;
    }
    if (raw === needle || raw === `DN${needle}`) {
      return value;
    }
  }
  return null;
}

export function matchWaysFacet(
  values: readonly string[],
  ways: Exclude<QuizWays, "skip">,
): string | null {
  for (const value of values) {
    const raw = value.trim();
    if (ways === "2" && /2\s*[-–—]?\s*ход/i.test(raw)) {
      return value;
    }
    if (ways === "3" && /3\s*[-–—]?\s*ход/i.test(raw)) {
      return value;
    }
  }
  return null;
}

const KVS_BAND_LIMITS: Record<
  Exclude<QuizKvs, "skip">,
  { min: number; max: number }
> = {
  up_to_2_5: { min: 0, max: 2.5 },
  "2_5_to_6": { min: 2.5, max: 6.3 },
  "6_to_16": { min: 6.3, max: 16 },
  "16_to_40": { min: 16, max: 40 },
  over_40: { min: 40, max: 999 },
};

function kvsInBand(kvs: number, choice: Exclude<QuizKvs, "skip">): boolean {
  switch (choice) {
    case "up_to_2_5":
      return kvs <= KVS_BAND_LIMITS.up_to_2_5.max + 0.001;
    case "2_5_to_6":
      return (
        kvs > KVS_BAND_LIMITS.up_to_2_5.max + 0.001 &&
        kvs <= KVS_BAND_LIMITS["2_5_to_6"].max + 0.001
      );
    case "6_to_16":
      return (
        kvs > KVS_BAND_LIMITS["2_5_to_6"].max + 0.001 &&
        kvs <= KVS_BAND_LIMITS["6_to_16"].max + 0.001
      );
    case "16_to_40":
      return (
        kvs > KVS_BAND_LIMITS["6_to_16"].max + 0.001 &&
        kvs <= KVS_BAND_LIMITS["16_to_40"].max + 0.001
      );
    case "over_40":
      return kvs > KVS_BAND_LIMITS["16_to_40"].max + 0.001;
    default:
      return false;
  }
}

/** Parse catalog Kvs label (``1,6``, ``10,1 м³/ч``) to m³/h. */
export function parseKvsM3h(value: string): number | null {
  const token = value.trim().split(/\s/)[0]?.replace(",", ".");
  if (!token) {
    return null;
  }
  const parsed = Number.parseFloat(token);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Pick catalog Kvs values in the quiz band (comma OR for the API).
 * All chips in-band are kept so DN65–150 / 8100Q are not dropped when the
 * band also contains other Kvs (e.g. «больше 40» → 63,100,160…).
 */
export function matchKvsFacet(
  values: readonly string[],
  choice: Exclude<QuizKvs, "skip">,
): string | null {
  const inBand = values
    .map((value) => ({ value, kvs: parseKvsM3h(value) }))
    .filter((row): row is { value: string; kvs: number } => row.kvs !== null)
    .filter((row) => kvsInBand(row.kvs, choice))
    .sort((a, b) => a.kvs - b.kvs);

  if (inBand.length === 0) {
    return null;
  }

  return [...new Set(inBand.map((row) => row.value))].join(",");
}

export function facetValuesForKey(
  facets: readonly CatalogFacet[],
  key: string,
): string[] {
  const facet = facets.find((row) => row.key === key);
  if (!facet) {
    return [];
  }
  return facet.values.map((row) => row.value);
}
