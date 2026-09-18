import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { MessengerLinks } from "./MessengerLinks";

const telegramChannel = {
  channel: "telegram_support_bot",
  label: "Telegram",
  deep_link: "https://t.me/HooconMsk_bot?start=support",
  provider: "telegram",
  kind: "bot",
} as const;

const maxChannel = {
  channel: "max_support_bot",
  label: "MAX",
  deep_link: "https://max.ru/u/123",
  provider: "max",
  kind: "bot",
} as const;

describe("MessengerLinks", () => {
  it("renders semantic list items without role=listitem on links", () => {
    const html = renderToStaticMarkup(
      <MessengerLinks channels={[telegramChannel]} variant="footer" />,
    );

    expect(html).toContain('<ul class="_footerRow_');
    expect(html).toContain("<li");
    expect(html).not.toContain('role="listitem"');
  });

  it("keeps accessible label on Telegram icon-only footer link", () => {
    const html = renderToStaticMarkup(
      <MessengerLinks channels={[telegramChannel]} variant="footer" />,
    );

    expect(html).toContain('aria-label="Telegram"');
    expect(html).not.toContain('aria-hidden="true"');
    expect(html).toContain('viewBox="0 0 131 42"');
    expect(html).toContain('fill-rule="evenodd"');
    expect(html).not.toContain("#2aabee");
  });

  it("keeps accessible label on MAX icon-only footer link", () => {
    const html = renderToStaticMarkup(
      <MessengerLinks channels={[maxChannel]} variant="footer" />,
    );

    expect(html).toContain('aria-label="MAX"');
    expect(html).not.toContain('aria-hidden="true"');
  });

  it("uses the same logo height for MAX and Telegram footer buttons", () => {
    const css = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "MessengerLinks.module.css"),
      "utf8",
    );
    const footerRule = css.split(".footerIconMax,\n.footerIconTelegram {")[1].split("}")[0];

    expect(footerRule).toContain("height: 1.5rem");
    expect(footerRule).toContain("width: auto");
  });
});
