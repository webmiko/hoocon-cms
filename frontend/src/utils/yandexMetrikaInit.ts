/** Match Metrika cabinet init (webvisor + ecommerce dataLayer). */
export function yandexMetrikaInitOptions(
  referrer: string = document.referrer,
  url: string = location.href,
) {
  return {
    webvisor: true,
    clickmap: true,
    ecommerce: "dataLayer",
    referrer,
    url,
    accurateTrackBounce: true,
    trackLinks: true,
  } as const;
}
