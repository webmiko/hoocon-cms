import { expect, test } from "@playwright/test";

import {
  openSupportWebChat,
  primeCookieConsent,
  submitRfqForm,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await primeCookieConsent(page);
});

test("support widget sends a visitor message", async ({ page }) => {
  const message = "E2E: вопрос по приводу DA2MU для теста чата";

  await page.goto("/");
  await openSupportWebChat(page);

  await page.getByPlaceholder("Сообщение…").fill(message);
  await page.getByRole("button", { name: "Отправить" }).click();

  await expect(page.getByText(message, { exact: true })).toBeVisible({
    timeout: 15_000,
  });
});

test("RFQ form submits successfully", async ({ page }) => {
  await page.goto("/rfq");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "коммерческого предложения",
  );

  await submitRfqForm(page, {
    name: "E2E Тест",
    email: "e2e-smoke@example.com",
    company: "ООО «E2E Smoke»",
    message: "E2E: прошу КП на 10 приводов для smoke-теста.",
  });

  await expect(page.getByRole("heading", { name: "Заявка отправлена" })).toBeVisible({
    timeout: 15_000,
  });
});
