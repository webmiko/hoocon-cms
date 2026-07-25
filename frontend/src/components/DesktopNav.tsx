import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { countVisibleNavItems, DESKTOP_NAV_ITEMS } from "../utils/navOverflow";
import styles from "./Layout.module.css";

function pathMatches(pathname: string, to: string): boolean {
  if (to === "/") {
    return pathname === "/";
  }
  return pathname === to || pathname.startsWith(`${to}/`);
}

/**
 * Desktop primary nav with Priority+ overflow into «Ещё».
 * Keeps a single row; items that do not fit move into a dropdown.
 */
export function DesktopNav() {
  const location = useLocation();
  const navRef = useRef<HTMLElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const moreMeasureRef = useRef<HTMLButtonElement>(null);
  const moreWrapRef = useRef<HTMLDivElement>(null);
  const moreMenuId = useId();

  const [visibleCount, setVisibleCount] = useState(DESKTOP_NAV_ITEMS.length);
  const [moreOpen, setMoreOpen] = useState(false);
  const [menuPath, setMenuPath] = useState(location.pathname);

  if (menuPath !== location.pathname) {
    setMenuPath(location.pathname);
    if (moreOpen) {
      setMoreOpen(false);
    }
  }

  useLayoutEffect(() => {
    const nav = navRef.current;
    const measure = measureRef.current;
    const moreMeasure = moreMeasureRef.current;
    if (!nav || !measure || !moreMeasure) {
      return;
    }

    function recalc() {
      if (!nav || !measure || !moreMeasure) {
        return;
      }
      const itemEls = Array.from(
        measure.querySelectorAll<HTMLElement>("[data-nav-measure]"),
      );
      // Read all geometry in one frame, then setState once (avoid layout thrash).
      const navWidth = nav.clientWidth;
      const widths = itemEls.map((el) => el.offsetWidth);
      const moreWidth = moreMeasure.offsetWidth;
      setVisibleCount(countVisibleNavItems(navWidth, widths, moreWidth));
    }

    let raf = 0;
    const scheduleRecalc = () => {
      if (raf) {
        return;
      }
      raf = requestAnimationFrame(() => {
        raf = 0;
        recalc();
      });
    };

    scheduleRecalc();
    const observer = new ResizeObserver(scheduleRecalc);
    observer.observe(nav);
    void document.fonts?.ready.then(scheduleRecalc);

    return () => {
      if (raf) {
        cancelAnimationFrame(raf);
      }
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!moreOpen) {
      return;
    }
    function onPointerDown(event: MouseEvent) {
      const root = moreWrapRef.current;
      if (root && !root.contains(event.target as Node)) {
        setMoreOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMoreOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [moreOpen]);

  const visible = DESKTOP_NAV_ITEMS.slice(0, visibleCount);
  const overflow = DESKTOP_NAV_ITEMS.slice(visibleCount);
  const overflowActive = overflow.some((item) =>
    pathMatches(location.pathname, item.to),
  );

  return (
    <nav ref={navRef} className={styles.navDesktop} aria-label="Основное меню">
      <div className={styles.navMeasure} ref={measureRef} aria-hidden="true">
        {DESKTOP_NAV_ITEMS.map((item) => (
          <span key={item.to} data-nav-measure className={styles.navLink}>
            {item.label}
          </span>
        ))}
        <button
          ref={moreMeasureRef}
          type="button"
          tabIndex={-1}
          className={styles.navMoreButton}
        >
          Ещё
          <span className={styles.navMoreCaret} aria-hidden="true" />
        </button>
      </div>

      <div className={styles.navDesktopInner}>
        {visible.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className={
              pathMatches(location.pathname, item.to)
                ? `${styles.navLink} ${styles.navLinkActive}`
                : styles.navLink
            }
          >
            {item.label}
          </Link>
        ))}

        {overflow.length > 0 ? (
          <div className={styles.navMore} ref={moreWrapRef}>
            <button
              type="button"
              className={
                overflowActive || moreOpen
                  ? `${styles.navMoreButton} ${styles.navMoreButtonOpen}`
                  : styles.navMoreButton
              }
              aria-expanded={moreOpen}
              aria-controls={moreMenuId}
              aria-haspopup="menu"
              onClick={() => setMoreOpen((open) => !open)}
            >
              Ещё
              <span className={styles.navMoreCaret} aria-hidden="true" />
            </button>
            {moreOpen ? (
              <ul id={moreMenuId} className={styles.navMoreMenu} role="menu">
                {overflow.map((item) => (
                  <li key={item.to} role="none">
                    <Link
                      to={item.to}
                      role="menuitem"
                      className={
                        pathMatches(location.pathname, item.to)
                          ? `${styles.navMoreItem} ${styles.navMoreItemActive}`
                          : styles.navMoreItem
                      }
                      onClick={() => setMoreOpen(false)}
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </nav>
  );
}
