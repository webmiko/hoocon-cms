/** Drop the fragment and credential query keys before a URL leaves the page. */
export function urlWithoutCredentials(value: string): string {
  const hashless = value.split("#")[0] ?? "";
  try {
    const url = new URL(hashless, "https://hoocon.local");
    url.searchParams.delete("t");
    url.searchParams.delete("token");
    if (hashless.startsWith("http://") || hashless.startsWith("https://")) {
      return url.toString();
    }
    const search = url.searchParams.toString();
    return search ? `${url.pathname}?${search}` : url.pathname;
  } catch {
    return hashless;
  }
}

/** Match Metrika cabinet init (webvisor + ecommerce dataLayer). */
export function yandexMetrikaInitOptions(
  referrer: string = typeof document === "undefined" ? "" : document.referrer,
  url: string = typeof location === "undefined" ? "/" : location.href,
) {
  return {
    webvisor: true,
    clickmap: true,
    ecommerce: "dataLayer",
    referrer: urlWithoutCredentials(referrer),
    url: urlWithoutCredentials(url),
    accurateTrackBounce: true,
    trackLinks: true,
  } as const;
}
