import { afterEach, describe, expect, it } from "vitest";

import {
  installServerCrawlRetirement,
  pageNodeIsReady,
  pageTextIsReady,
  retireServerCrawl,
  serverCrawlIsShowing,
} from "./serverCrawl";

const ERROR_SENTENCE = "Произошла ошибка. Попробуйте обновить страницу.";
const HOME_COPY =
  "Электроприводы для вентиляции и кондиционирования. Подбор модели за минуту, каталог, паспорта PDF.";

afterEach(() => {
  document.body.innerHTML = "";
  document.documentElement.removeAttribute("data-theme");
});

describe("pageTextIsReady", () => {
  it("rejects the shell sentences Yandex was using as snippets", () => {
    expect(pageTextIsReady("Загрузка…")).toBe(false);
    expect(pageTextIsReady(ERROR_SENTENCE)).toBe(false);
    expect(pageTextIsReady("Не удалось загрузить страницу после обновления сайта.")).toBe(false);
    expect(pageTextIsReady(HOME_COPY)).toBe(true);
  });
});

describe("pageNodeIsReady", () => {
  it("waits for a real heading and ignores a loading or crash line", () => {
    const host = document.createElement("div");
    host.innerHTML = "<p>Загрузка…</p>";
    expect(pageNodeIsReady(host)).toBe(false);

    host.innerHTML = `<p>${ERROR_SENTENCE}</p>`;
    expect(pageNodeIsReady(host)).toBe(false);

    host.innerHTML = "<h1>Привод DA3</h1><p>Артикул DA3, момент 5 Н·м.</p>";
    expect(pageNodeIsReady(host)).toBe(true);

    host.innerHTML = "<h1>Документация</h1>";
    expect(pageNodeIsReady(host)).toBe(true);
  });
});

describe("installServerCrawlRetirement", () => {
  it("keeps the article while the shell is loading, then removes it for a real heading", async () => {
    document.body.innerHTML = `
      <article id="seo-crawl"><h1>Электроприводы</h1><p>${HOME_COPY}</p></article>
      <div id="root" inert aria-hidden="true"><main id="main-content"><p>Загрузка…</p></main></div>
    `;
    const stop = installServerCrawlRetirement();
    expect(serverCrawlIsShowing()).toBe(true);
    expect(document.getElementById("root")?.hasAttribute("inert")).toBe(true);
    expect(document.getElementById("root")?.getAttribute("aria-hidden")).toBe("true");

    const main = document.getElementById("main-content");
    main!.innerHTML = `<h1>Каталог продукции</h1><p>${HOME_COPY}</p>`;
    await Promise.resolve();

    expect(document.getElementById("seo-crawl")).toBeNull();
    expect(document.getElementById("root")?.hasAttribute("aria-hidden")).toBe(false);
    expect(document.getElementById("root")?.hasAttribute("inert")).toBe(false);
    stop();
  });

  it("does not drop the article when the only mutation is the error sentence", async () => {
    document.body.innerHTML = `
      <article id="seo-crawl"><h1>Электроприводы</h1><p>${HOME_COPY}</p></article>
      <div id="root" aria-hidden="true"><main id="main-content"></main></div>
    `;
    const stop = installServerCrawlRetirement();
    document.getElementById("main-content")!.textContent = ERROR_SENTENCE;
    await Promise.resolve();
    expect(serverCrawlIsShowing()).toBe(true);
    stop();
    retireServerCrawl();
  });
});
