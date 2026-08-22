/** Ids must stay in sync with ``backend/config/seo/spa_index.py``. */
export const HOME_SSR_HERO_ID = "hoocon-ssr-hero";
export const HOME_LCP_BOOT_ID = "hoocon-lcp-boot";
export const HOME_SSR_HERO_CSS_ID = "hoocon-ssr-hero-css";

const FADE_MS = 320;

/**
 * Fade out the SSR hero overlay, then remove it after the transition.
 *
 * The SSR hero image stays as the LCP element — it is never moved or re-painted.
 * On interaction (scroll/click/keydown) we fade the overlay so the React hero
 * underneath becomes visible. Removing the element after fade does not create
 * a new LCP candidate.
 */
export function fadeOutHomeSsrHero(): void {
  const hero = document.getElementById(HOME_SSR_HERO_ID);
  if (!hero) {
    return;
  }
  hero.style.transition = `opacity ${FADE_MS}ms ease`;
  hero.style.opacity = "0";
  window.setTimeout(() => {
    hero.remove();
    dismissHomeSsrHero();
  }, FADE_MS);
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
