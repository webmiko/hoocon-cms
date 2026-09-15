import { expect, test } from "@playwright/test";

import { primeCookieConsent, SMOKE_SKU_PATH } from "./helpers";

test.beforeEach(async ({ page }) => {
  await primeCookieConsent(page);
});

test("catalog page loads", async ({ page }) => {
  await page.goto("/catalog");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Каталог");
});

test("PDP shows seeded published SKU", async ({ page }) => {
  await page.goto(SMOKE_SKU_PATH);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("HVA");
});

test("RFQ form is available", async ({ page }) => {
  await page.goto("/rfq");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "коммерческого предложения",
  );
  await expect(
    page.getByRole("button", { name: "Отправить заявку" }),
  ).toBeVisible();
});
