/**
 * Compact labels for catalog facet chips / active tags.
 *
 * API keeps Belimo-full values (e.g. voltage); the sidebar shows short forms.
 */

const FACET_LABEL_SHORT: Record<string, string> = {
  moment: "Момент",
  voltage: "Напряжение",
  control: "Управление",
  area: "Площадь",
  aux_switch: "Вспом. перекл.",
  dn: "DN",
  ways: "Вид крана",
  kvs: "Kvs (м³/ч)",
};

/**
 * Short sidebar / tag label for a facet key.
 *
 * Args:
 *   key: Canonical facet key from the API.
 *   fallback: Backend label when no short map entry exists.
 */
export function facetLabelShort(key: string, fallback: string): string {
  return FACET_LABEL_SHORT[key] ?? fallback;
}

/**
 * Compact value text for narrow filter UI (URL still uses the API value).
 *
 * Args:
 *   key: Facet key.
 *   value: Canonical API value.
 */
export function facetValueShort(key: string, value: string): string {
  const raw = value.trim();
  if (!raw) return raw;

  if (key === "voltage") {
    if (/100\s*[.…\-−–—]+\s*240|230/.test(raw)) return "100…240 В";
    if (/\b24\b/.test(raw)) return "24 В AC/DC";
  }

  if (key === "control") {
    if (/пропорциональн|модулир|плавн/i.test(raw)) return "Пропорциональное";
    if (/открыто|закрыто|вкл/i.test(raw)) return "Открыто/закрыто";
    if (/2-\/3|2\/3|позицион/i.test(raw)) return "2-/3-позиционное";
  }

  if (key === "area") {
    return raw
      .replace(/\s*\([^)]*\)\s*/g, " ")
      .replace(/(\d),\s+(\d)/g, "$1,$2")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/^(до\s+)?(\d+(?:[.,]\d+)?)\s*(?:м²|m²|м2|m2)?$/i, (_m, _upto, num) => {
        return `до ${String(num).replace(".", ",")} м²`;
      });
  }

  return raw;
}
