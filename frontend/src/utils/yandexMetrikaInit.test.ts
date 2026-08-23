import { describe, expect, it } from "vitest";

import { yandexMetrikaInitOptions } from "./yandexMetrikaInit";

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
});
