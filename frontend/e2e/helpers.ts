import { expect, type Page } from "@playwright/test";

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
    // Prefer web chat when messenger bots are configured in Admin.
    localStorage.setItem("hoocon-support-surface", "web");
  });
}

/** Open the floating support widget in web-chat mode. */
export async function openSupportWebChat(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Открыть чат поддержки" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  const webChatBtn = page.getByRole("button", { name: "Чат на сайте" });
  if (await webChatBtn.isVisible()) {
    await webChatBtn.click();
  }

  await expect(page.getByRole("heading", { name: "Поддержка Hoocon" })).toBeVisible();
  await expect(page.getByPlaceholder("Сообщение…")).toBeVisible();
}

export type RfqFormData = {
  name: string;
  email: string;
  company: string;
  message: string;
};

/** Fill and submit the RFQ lead form (PDn consent included). */
export async function submitRfqForm(page: Page, data: RfqFormData): Promise<void> {
  await page.locator("#name").fill(data.name);
  await page.locator("#email").fill(data.email);
  await page.locator("#company").fill(data.company);
  await page.locator("#message").fill(data.message);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Отправить заявку" }).click();
}
