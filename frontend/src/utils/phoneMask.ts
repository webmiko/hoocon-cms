/**
 * Phone mask for RU / BY / EAEU (Customs Union) country codes.
 * Display: ``+7 (999) 999-99-99``; stored value matches display (max 50).
 */

export type PhoneCountryId = "ru" | "by" | "kz" | "am" | "kg";

export type PhoneCountry = {
  id: PhoneCountryId;
  /** Select label, e.g. ``Россия +7``. */
  label: string;
  /** Digits after ``+`` (no plus). */
  dial: string;
  /** Max national significant digits (without country code). */
  nationalLength: number;
  /** Example placeholder for the national part. */
  placeholder: string;
};

export const PHONE_COUNTRIES: readonly PhoneCountry[] = [
  {
    id: "ru",
    label: "Россия +7",
    dial: "7",
    nationalLength: 10,
    placeholder: "(999) 999-99-99",
  },
  {
    id: "by",
    label: "Беларусь +375",
    dial: "375",
    nationalLength: 9,
    placeholder: "(29) 999-99-99",
  },
  {
    id: "kz",
    label: "Казахстан +7",
    dial: "7",
    nationalLength: 10,
    placeholder: "(700) 999-99-99",
  },
  {
    id: "am",
    label: "Армения +374",
    dial: "374",
    nationalLength: 8,
    placeholder: "99 999-999",
  },
  {
    id: "kg",
    label: "Кыргызстан +996",
    dial: "996",
    nationalLength: 9,
    placeholder: "999 999-999",
  },
] as const;

const BY_ID: PhoneCountryId = "by";
const AM_ID: PhoneCountryId = "am";
const KG_ID: PhoneCountryId = "kg";
const RU_ID: PhoneCountryId = "ru";

export function phoneCountryById(id: PhoneCountryId): PhoneCountry {
  const found = PHONE_COUNTRIES.find((c) => c.id === id);
  return found ?? PHONE_COUNTRIES[0]!;
}

/** Digits only. */
export function digitsOnly(value: string): string {
  return value.replace(/\D/g, "");
}

/**
 * Format national digits for a country (no country code in output).
 * RU/KZ: ``(999) 999-99-99`` · BY: ``(29) 999-99-99`` · AM/KG similar.
 */
export function formatNational(
  countryId: PhoneCountryId,
  nationalDigits: string,
): string {
  const country = phoneCountryById(countryId);
  const d = digitsOnly(nationalDigits).slice(0, country.nationalLength);
  if (!d) return "";

  if (countryId === "ru" || countryId === "kz") {
    // (XXX) XXX-XX-XX
    const a = d.slice(0, 3);
    const b = d.slice(3, 6);
    const c = d.slice(6, 8);
    const e = d.slice(8, 10);
    let out = `(${a}`;
    if (d.length >= 3) out += ")";
    if (b) out += ` ${b}`;
    if (c) out += `-${c}`;
    if (e) out += `-${e}`;
    return out;
  }

  if (countryId === "by") {
    // (XX) XXX-XX-XX
    const a = d.slice(0, 2);
    const b = d.slice(2, 5);
    const c = d.slice(5, 7);
    const e = d.slice(7, 9);
    let out = `(${a}`;
    if (d.length >= 2) out += ")";
    if (b) out += ` ${b}`;
    if (c) out += `-${c}`;
    if (e) out += `-${e}`;
    return out;
  }

  if (countryId === "am") {
    // XX XXX-XXX
    const a = d.slice(0, 2);
    const b = d.slice(2, 5);
    const c = d.slice(5, 8);
    let out = a;
    if (b) out += ` ${b}`;
    if (c) out += `-${c}`;
    return out;
  }

  // kg: XXX XXX-XXX
  const a = d.slice(0, 3);
  const b = d.slice(3, 6);
  const c = d.slice(6, 9);
  let out = a;
  if (b) out += ` ${b}`;
  if (c) out += `-${c}`;
  return out;
}

/** Full display value: ``+7 (999) 123-45-67``. Empty national → ``+7``. */
export function formatPhone(
  countryId: PhoneCountryId,
  nationalDigits: string,
): string {
  const country = phoneCountryById(countryId);
  const national = formatNational(countryId, nationalDigits);
  return national ? `+${country.dial} ${national}` : `+${country.dial}`;
}

export type ParsedPhone = {
  countryId: PhoneCountryId;
  nationalDigits: string;
};

/**
 * Guess country + national digits from a stored/pasted value.
 * Longer dial codes win (375 before 7). Default Russia.
 */
export function parsePhone(raw: string): ParsedPhone {
  const all = digitsOnly(raw);
  if (!all) {
    return { countryId: RU_ID, nationalDigits: "" };
  }

  const ordered: PhoneCountryId[] = [BY_ID, AM_ID, KG_ID, RU_ID];
  // Prefer explicit BY/AM/KG prefixes; +7 → RU (KZ is manual select).
  for (const id of ordered) {
    if (id === RU_ID) continue;
    const dial = phoneCountryById(id).dial;
    if (all.startsWith(dial)) {
      const national = all.slice(dial.length).slice(0, phoneCountryById(id).nationalLength);
      return { countryId: id, nationalDigits: national };
    }
  }

  if (all.startsWith("7")) {
    return {
      countryId: RU_ID,
      nationalDigits: all.slice(1).slice(0, 10),
    };
  }

  // Bare national digits (no country) — treat as RU.
  return {
    countryId: RU_ID,
    nationalDigits: all.slice(0, 10),
  };
}

/**
 * Apply typed/pasted input for the national field.
 * ``rawInput`` is the whole input value (may include formatting chars).
 */
export function nationalFromInput(
  countryId: PhoneCountryId,
  rawInput: string,
): string {
  const country = phoneCountryById(countryId);
  return digitsOnly(rawInput).slice(0, country.nationalLength);
}

/** IANA zones → EAEU phone country (IP geo not required). */
const TZ_TO_COUNTRY: Readonly<Record<string, PhoneCountryId>> = {
  "Europe/Minsk": BY_ID,
  "Asia/Yerevan": AM_ID,
  "Asia/Bishkek": KG_ID,
  "Asia/Almaty": "kz",
  "Asia/Aqtobe": "kz",
  "Asia/Atyrau": "kz",
  "Asia/Oral": "kz",
  "Asia/Qostanay": "kz",
  "Asia/Qyzylorda": "kz",
  "Asia/Aqtau": "kz",
};

/**
 * Guess phone country from timezone + Accept-Language (browser geo signals).
 * No IP API / Geolocation permission. Unknown → Russia.
 */
export function guessPhoneCountryFromGeo(
  timeZone?: string,
  languages?: readonly string[],
): PhoneCountryId {
  const tz =
    timeZone
    ?? (typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : "");
  if (tz && TZ_TO_COUNTRY[tz]) {
    return TZ_TO_COUNTRY[tz];
  }

  const langs =
    languages
    ?? (typeof navigator !== "undefined"
      ? [...(navigator.languages ?? []), navigator.language]
      : []);

  for (const raw of langs) {
    const tag = (raw || "").toLowerCase();
    if (!tag) continue;
    if (tag === "be" || tag.startsWith("be-") || tag === "ru-by") return BY_ID;
    if (tag === "kk" || tag.startsWith("kk-") || tag === "ru-kz") return "kz";
    if (tag === "hy" || tag.startsWith("hy-") || tag === "ru-am") return AM_ID;
    if (tag === "ky" || tag.startsWith("ky-") || tag === "ru-kg") return KG_ID;
  }

  return RU_ID;
}
