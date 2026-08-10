/** Ids must stay in sync with ``backend/config/seo/spa_index.py``. */
export const HOME_SSR_HERO_ID = "hoocon-ssr-hero";
export const HOME_LCP_BOOT_ID = "hoocon-lcp-boot";
export const HOME_SSR_HERO_CSS_ID = "hoocon-ssr-hero-css";

/**
 * Move the server-painted LCP ``<img>`` into the React hero slide.
 *
 * Keeps the same DOM node so mobile LCP is not reset when ``createRoot``
 * mounts (SSR shell lives outside ``#root``).
 *
 * Args:
 *   host: First hero slide element that should own the boot image.
 *   className: React slide image class to apply on the boot node.
 *
 * Returns:
 *   True when the boot image was adopted.
 */
export function adoptHomeSsrLcpImage(
  host: HTMLElement,
  className: string,
): boolean {
  const boot = document.getElementById(HOME_LCP_BOOT_ID);
  if (!(boot instanceof HTMLImageElement)) {
    dismissHomeSsrHero();
    return false;
  }
  boot.className = className;
  boot.decoding = "sync";
  boot.fetchPriority = "high";
  host.appendChild(boot);
  dismissHomeSsrHero();
  return true;
}

/** Remove leftover home SSR shell + critical CSS (route change / no boot). */
export function dismissHomeSsrHero(): void {
  document.getElementById(HOME_SSR_HERO_ID)?.remove();
  document.getElementById(HOME_SSR_HERO_CSS_ID)?.remove();
}

/** True when the full-page boot hero image is still in the document. */
export function homeSsrLcpBootPresent(): boolean {
  return document.getElementById(HOME_LCP_BOOT_ID) instanceof HTMLImageElement;
}
