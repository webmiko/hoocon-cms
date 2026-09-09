/** Empty sticky-dock CTA: catalog KP vs navigate to catalog vs OEM mailto. */

export type EmptyDockCtaChoice =
  | { kind: "to"; to: string; label: string; shortLabel: string }
  | { kind: "href"; href: string; label: string; shortLabel: string };

const ZAVOD_FACTORY_MAILTO =
  "mailto:hoocon@hoocon.com.cn?subject=OEM%20inquiry%20from%20hoocon.ru";

/** True for /catalog and nested catalog routes (SKU / category). */
export function isCatalogRoute(pathname: string): boolean {
  return pathname === "/catalog" || pathname.startsWith("/catalog/");
}

/**
 * Empty CompareTray CTA by route.
 * Catalog keeps «Запросить КП»; elsewhere (except OEM /zavod) → «В каталог».
 */
export function emptyDockCtaForPath(
  pathname: string,
  options?: { zavodMailto?: string },
): EmptyDockCtaChoice {
  if (/^\/zavod\/?$/.test(pathname)) {
    return {
      kind: "href",
      href: options?.zavodMailto ?? ZAVOD_FACTORY_MAILTO,
      label: "Связаться с заводом",
      shortLabel: "OEM",
    };
  }
  if (isCatalogRoute(pathname)) {
    return {
      kind: "to",
      to: "/consultation",
      label: "Запросить КП",
      shortLabel: "КП",
    };
  }
  return {
    kind: "to",
    to: "/catalog",
    label: "В каталог",
    shortLabel: "Каталог",
  };
}
