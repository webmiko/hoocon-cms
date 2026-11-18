/**
 * Server article ``#seo-crawl`` is the visible page until the SPA paints a
 * real heading. Yandex executes JS and snapshots the DOM: if ``createRoot``
 * has already wiped the only copy of the text, the snippet becomes
 * «Загрузка…» or the error-boundary sentence.
 */

const SHELL_PHRASES = [
  "Произошла ошибка. Попробуйте обновить страницу.",
  "Не удалось загрузить страницу после обновления сайта.",
  "Не удалось загрузить страницу",
  "Проверьте соединение и попробуйте ещё раз.",
  "Не удалось загрузить статьи.",
  "Не удалось загрузить новости.",
  "Ошибка загрузки каталога. Попробуйте позже.",
  "Загрузка объектов…",
  "Загрузка…",
  "Обновить страницу",
] as const;

/** Headings that are the shell, not the page. Keep the server article. */
const SHELL_H1_RE = /^(?:Произошла ошибка|Загрузка)/;

const READY_TEXT_MIN = 40;

export function serverCrawlIsShowing(doc: Document = document): boolean {
  return doc.getElementById("seo-crawl") != null;
}

/**
 * True when ``text`` still describes the page after shell sentences are removed.
 */
export function pageTextIsReady(text: string): boolean {
  let clean = text.replace(/\s+/g, " ").trim();
  for (const phrase of SHELL_PHRASES) {
    clean = clean.split(phrase).join(" ");
  }
  clean = clean.replace(/\s+/g, " ").trim();
  return clean.length >= READY_TEXT_MIN;
}

/**
 * True when the SPA scope has a real heading or enough non-shell text.
 * A lone «Загрузка…» or the error-boundary sentence is not ready.
 */
export function pageNodeIsReady(scope: ParentNode): boolean {
  const heading = scope.querySelector("h1");
  const title = (heading?.textContent ?? "").replace(/\s+/g, " ").trim();
  if (title && !SHELL_H1_RE.test(title)) {
    return true;
  }
  return pageTextIsReady(scope.textContent ?? "");
}

function crawlScope(doc: Document): ParentNode | null {
  return doc.getElementById("main-content") ?? doc.getElementById("root");
}

/** Drop the server article and let #root paint. No-op when it is already gone. */
export function retireServerCrawl(doc: Document = document): void {
  const root = doc.getElementById("root");
  root?.removeAttribute("aria-hidden");
  root?.removeAttribute("inert");
  doc.getElementById("seo-crawl")?.remove();
}

/**
 * Remove the server article once the route has painted real content.
 * Returns a stop function (tests).
 */
export function installServerCrawlRetirement(doc: Document = document): () => void {
  if (!serverCrawlIsShowing(doc)) {
    return () => {};
  }
  let stopped = false;
  const consider = () => {
    if (stopped) return;
    const scope = crawlScope(doc);
    if (!scope || !pageNodeIsReady(scope)) return;
    stopped = true;
    observer.disconnect();
    retireServerCrawl(doc);
  };
  const observer = new MutationObserver(consider);
  if (doc.body) {
    observer.observe(doc.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }
  consider();
  return () => {
    stopped = true;
    observer.disconnect();
  };
}
