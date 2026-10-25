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

function browserHref(): string {
  if (typeof location === "undefined") {
    return "/";
  }
  try {
    return location.href || "/";
  } catch {
    return "/";
  }
}

function browserReferrer(): string {
  if (typeof document === "undefined") {
    return "";
  }
  return document.referrer || "";
}

/** Absolute URL with the quote token and the fragment already removed. */
export function absoluteAnalyticsUrl(value: string): string {
  const cleaned = urlWithoutCredentials(value || "/");
  if (cleaned.startsWith("http://") || cleaned.startsWith("https://")) {
    return cleaned;
  }
  let origin = "";
  if (typeof location !== "undefined") {
    try {
      if (location.origin && location.origin !== "null") {
        origin = location.origin;
      }
    } catch {
      origin = "";
    }
  }
  const path = cleaned.startsWith("/") ? cleaned : `/${cleaned}`;
  return origin ? `${origin}${path}` : path;
}

/**
 * page_location and page_referrer safe for GA4.
 *
 * The tag otherwise sends location.href, hash included, so a quote token
 * in ``#t=`` or ``?t=`` would leave the page.
 */
export function ga4TransportParams(
  href: string = browserHref(),
  referrer: string = browserReferrer(),
): { page_location: string; page_referrer: string } {
  return {
    page_location: absoluteAnalyticsUrl(href),
    page_referrer: referrer ? absoluteAnalyticsUrl(referrer) : "",
  };
}

/** Config payload: the first page_view must use the cleaned URL. */
export function ga4ConfigParams(
  href?: string,
  referrer?: string,
): { page_location: string; page_referrer: string; send_page_view: true } {
  return { ...ga4TransportParams(href, referrer), send_page_view: true };
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
