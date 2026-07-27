/**
 * Path "depth" for mobile/PWA card slide direction.
 * Deeper → slide up; shallower → slide down.
 */

export type NavSlideDirection = "up" | "down" | "none";

/**
 * Rough hierarchy depth for list → detail transitions.
 */
export function navPathDepth(pathname: string): number {
  if (/^\/catalog\/[^/]+\/[^/]+/.test(pathname)) {
    return 3; // SKU PDP
  }
  if (/^\/catalog\/[^/]+/.test(pathname)) {
    return 2; // category
  }
  if (pathname.startsWith("/catalog") || pathname === "/compare") {
    return 1;
  }
  if (/^\/(?:statyi|novosti)\/[^/]+/.test(pathname)) {
    return 2;
  }
  if (pathname === "/statyi" || pathname === "/novosti") {
    return 1;
  }
  if (
    pathname === "/consultation" ||
    pathname === "/replacement" ||
    pathname === "/search"
  ) {
    return 1;
  }
  return 0;
}

/**
 * Decide slide direction from previous → next path.
 */
export function navSlideDirection(
  fromPathname: string,
  toPathname: string,
): NavSlideDirection {
  if (fromPathname === toPathname) {
    return "none";
  }
  const from = navPathDepth(fromPathname);
  const to = navPathDepth(toPathname);
  if (to > from) {
    return "up";
  }
  if (to < from) {
    return "down";
  }
  return "none";
}

/**
 * True when the app runs as an installed PWA (standalone / iOS home screen).
 */
export function isStandaloneDisplay(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  if (window.matchMedia("(display-mode: standalone)").matches) {
    return true;
  }
  const nav = window.navigator as Navigator & { standalone?: boolean };
  return nav.standalone === true;
}
