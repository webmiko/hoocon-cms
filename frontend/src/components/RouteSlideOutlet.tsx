import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useNavigationType } from "react-router-dom";

import {
  isStandaloneDisplay,
  navSlideDirection,
  type NavSlideDirection,
} from "../utils/navSlide";
import styles from "./RouteSlide.module.css";

/**
 * PWA page slide: deeper routes rise up, back slides down.
 *
 * Safari browser tabs often animate history already; standalone PWA does not —
 * this restores a similar «card» feel for catalog ↔ PDP (and list ↔ article).
 */
export function RouteSlideOutlet() {
  const location = useLocation();
  const navigationType = useNavigationType();
  const prevPathRef = useRef(location.pathname);
  const [slideAnim, setSlideAnim] = useState<NavSlideDirection>("none");
  const [enable, setEnable] = useState(false);
  const slide: NavSlideDirection = enable ? slideAnim : "none";

  useEffect(() => {
    const mq = window.matchMedia("(display-mode: standalone)");
    const sync = () => setEnable(isStandaloneDisplay());
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (!enable) {
      prevPathRef.current = location.pathname;
      return;
    }

    let direction = navSlideDirection(prevPathRef.current, location.pathname);
    if (navigationType === "POP" && direction === "up") {
      // History back should never read as «push up».
      direction = "down";
    }
    prevPathRef.current = location.pathname;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (direction === "none" || reduce.matches) {
      return;
    }

    let cancelled = false;
    // Defer setState out of the effect body (react-hooks/set-state-in-effect).
    const frame = window.requestAnimationFrame(() => {
      if (cancelled) return;
      setSlideAnim(direction);
    });
    const timer = window.setTimeout(() => {
      if (!cancelled) setSlideAnim("none");
    }, 380);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [location.pathname, location.key, navigationType, enable]);

  const className = [
    styles.stage,
    slide === "up" ? styles.slideUp : null,
    slide === "down" ? styles.slideDown : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={className} data-nav-slide={slide}>
      <Outlet />
    </div>
  );
}
