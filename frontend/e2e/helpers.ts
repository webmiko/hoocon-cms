import type { Page } from "@playwright/test";

/** Seeded by ``manage.py seed_e2e_smoke`` for Playwright smoke tests. */
export const SMOKE_SKU_PATH = "/catalog/vozdushnie/privod-hva-5nm";

/** Skip the first-visit cookie banner so smoke tests stay deterministic. */
export async function primeCookieConsent(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem(
      "hoocon-cookie-consent",
      JSON.stringify({
        version: 2,
        essential: true,
        analytics: false,
        marketing: false,
        updatedAt: new Date().toISOString(),
      }),
    );
  });
}
