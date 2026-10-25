import { describe, expect, it } from "vitest";

import { ga4ConfigParams, yandexMetrikaInitOptions } from "./yandexMetrikaInit";

describe("yandexMetrikaInitOptions", () => {
  it("matches Metrika cabinet flags for webvisor and ecommerce", () => {
    expect(yandexMetrikaInitOptions("https://ref.test/", "https://hoocon.ru/catalog/")).toEqual({
      webvisor: true,
      clickmap: true,
      ecommerce: "dataLayer",
      referrer: "https://ref.test/",
      url: "https://hoocon.ru/catalog/",
      accurateTrackBounce: true,
      trackLinks: true,
    });
  });

  it("drops the quote token from the hash and the query before Metrika sees the URL", () => {
    const options = yandexMetrikaInitOptions(
      "https://hoocon.ru/kp?t=secret&action=accept",
      "https://hoocon.ru/kp?t=secret#t=also-secret",
    );
    expect(options.referrer).not.toContain("secret");
    expect(options.url).not.toContain("secret");
    expect(options.url).not.toContain("#");
  });

  it("strips the quote token from the GA4 page URL and the referrer", () => {
    const params = ga4ConfigParams(
      "https://hoocon.ru/kp/offer?t=secret#t=also-secret",
      "https://hoocon.ru/kp?token=other",
    );
    expect(params.send_page_view).toBe(true);
    expect(params.page_location).toBe("https://hoocon.ru/kp/offer");
    expect(params.page_referrer).toBe("https://hoocon.ru/kp");
    expect(params.page_location).not.toContain("secret");
    expect(params.page_referrer).not.toContain("other");
  });
});
