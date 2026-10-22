/** EAC declarations shown on /dokumentaciya. View on the page, not a download. */

export type EacDeclaration = {
  id: string;
  src: string;
  width: number;
  height: number;
  title: string;
  alt: string;
  /** Docs hub series chips this declaration covers. */
  series: readonly string[];
  /** Lowercase text used by the page search. */
  search: string;
};

export const EAC_DECLARATIONS: readonly EacDeclaration[] = [
  {
    id: "eac-230v-2023",
    src: "/certificates/eac-230v-2023.webp",
    width: 724,
    height: 1024,
    title: "Декларация ЕАЭС N RU Д-CN.РА07.В.69603/23, электроприводы 230 В",
    alt:
      "Декларация о соответствии ЕАЭС N RU Д-CN.РА07.В.69603/23 "
      + "на электроприводы Hoocon 230 В серий DA, SA, HVA и HVD. "
      + "Зарегистрирована 20.09.2023, действует до 19.09.2028.",
    series: ["DA", "SA", "HV"],
    search:
      "декларация соответствие eac еаэс сертификат 230 da sa hva hvd hoocon 69603 2023 2028",
  },
  {
    id: "eac-24v-2024",
    src: "/certificates/eac-24v-2024.webp",
    width: 724,
    height: 1024,
    title: "Декларация о соответствии, электроприводы 24 В",
    alt:
      "Декларация о соответствии на электроприводы Hoocon 24 В "
      + "серий DA, SA, HVA и HVD. Зарегистрирована 19.09.2024, действует до 18.09.2029.",
    series: ["DA", "SA", "HV"],
    search:
      "декларация соответствие eac еаэс сертификат 24 da sa hva hvd hoocon 2024 2029",
  },
  {
    id: "eac-bv-2023",
    src: "/certificates/eac-bv-2023.webp",
    width: 724,
    height: 1024,
    title: "Декларация ЕАЭС N RU Д-CN.РА08.В.93029/23, краны шаровые",
    alt:
      "Декларация о соответствии ЕАЭС N RU Д-CN.РА08.В.93029/23 "
      + "на краны шаровые Hoocon серий BV, 8100-BV и 8100Q-BV. "
      + "Зарегистрирована 24.10.2023, действует до 19.10.2028.",
    series: ["BR"],
    search:
      "декларация соответствие eac еаэс сертификат кран шаровой арматура bv 8100 hoocon 93029 2023 2028",
  },
];

export function visibleEacDeclarations(filters: {
  q: string;
  series: string;
  kind: string;
}): EacDeclaration[] {
  if (filters.kind && filters.kind !== "certificate") {
    return [];
  }
  const series = filters.series.trim();
  const q = filters.q.trim().toLowerCase();
  return EAC_DECLARATIONS.filter((item) => {
    if (series && !item.series.includes(series)) {
      return false;
    }
    if (!q) {
      return true;
    }
    return q.split(/\s+/).every((part) => item.search.includes(part));
  });
}
