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

  it("hides decorative Telegram icon from assistive tech when text label is visible", () => {
    const html = renderToStaticMarkup(
      <MessengerLinks channels={[telegramChannel]} variant="footer" />,
    );

    expect(html).toContain('aria-hidden="true"');
    expect(html).not.toContain('aria-label=""');
    expect(html).toContain(">Telegram<");
  });

  it("keeps accessible label on MAX icon-only footer link", () => {
    const html = renderToStaticMarkup(
      <MessengerLinks channels={[maxChannel]} variant="footer" />,
    );

    expect(html).toContain('aria-label="MAX"');
    expect(html).not.toContain('aria-hidden="true"');
  });
});
