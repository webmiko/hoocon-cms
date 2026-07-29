import { useEffect, useId, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { CompareProvider } from "../compare/CompareContext";
import { CompareTray } from "./CompareTray";
import { CookieConsent } from "./CookieConsent";
import { Analytics } from "./Analytics";
import { DesktopNav } from "./DesktopNav";
import { RouteSlideOutlet } from "./RouteSlideOutlet";
import { ScrollProgress } from "./ScrollProgress";
import { ScrollToTop } from "./ScrollToTop";
import { StripTrailingSlash } from "./StripTrailingSlash";
import { BrandLogo } from "./BrandLogo";
import { ThemeToggle } from "./ThemeToggle";
import { openCookieConsentSettings } from "../utils/cookieConsent";
import { releaseLabel } from "../release";
import styles from "./Layout.module.css";

/** Hero «Запросить КП» on the home page — sticky CTA waits until it leaves the viewport. */
export const HERO_KP_CTA_ID = "hero-kp-cta";

/**
 * App shell: utility masthead + brand header + main + dark footer.
 *
 * Spec: docs/readiness-backend-ux.md §4.3; prototip-hoocon-shared.css.
 * No Cart/Wishlist (B2B without checkout in v1). Compare tray is not wishlist.
 */
export function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const routeKey = `${location.pathname}${location.search}`;
  const [menuRoute, setMenuRoute] = useState(routeKey);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const hideMobileCta =
    location.pathname.startsWith("/statyi") ||
    location.pathname.startsWith("/novosti");
  const isHome = location.pathname === "/";
  /** True while home hero «Запросить КП» intersects the viewport (mobile sticky waits). */
  const [heroKpVisible, setHeroKpVisible] = useState(true);
  const [homeTrack, setHomeTrack] = useState(isHome);

  // Reset hero visibility when navigating onto the home page.
  if (isHome !== homeTrack) {
    setHomeTrack(isHome);
    if (isHome) {
      setHeroKpVisible(true);
    }
  }

  const showMobileStickyCta = !hideMobileCta && !(isHome && heroKpVisible);

  // Close mobile menu when the route changes (adjust state during render).
  if (menuRoute !== routeKey) {
    setMenuRoute(routeKey);
    setMenuOpen(false);
  }

  useEffect(() => {
    const root = document.documentElement;
    if (!showMobileStickyCta) {
      root.dataset.stickyCta = "off";
    } else {
      delete root.dataset.stickyCta;
    }
    return () => {
      delete root.dataset.stickyCta;
    };
  }, [showMobileStickyCta]);

  useEffect(() => {
    if (hideMobileCta || !isHome) {
      return;
    }

    let cancelled = false;
    let observer: IntersectionObserver | null = null;

    function watch(el: Element) {
      observer = new IntersectionObserver(
        ([entry]) => {
          if (!cancelled) {
            setHeroKpVisible(entry.isIntersecting);
          }
        },
        { threshold: 0, rootMargin: "0px" },
      );
      observer.observe(el);
    }

    const existing = document.getElementById(HERO_KP_CTA_ID);
    if (existing) {
      watch(existing);
      return () => {
        cancelled = true;
        observer?.disconnect();
      };
    }

    // Home outlet may mount one frame after Layout's effect.
    const mo = new MutationObserver(() => {
      const el = document.getElementById(HERO_KP_CTA_ID);
      if (!el) return;
      mo.disconnect();
      watch(el);
    });
    mo.observe(document.body, { childList: true, subtree: true });
    return () => {
      cancelled = true;
      mo.disconnect();
      observer?.disconnect();
    };
  }, [hideMobileCta, isHome, routeKey]);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.body.dataset.menuOpen = "true";

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previous;
      delete document.body.dataset.menuOpen;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  function closeMenu() {
    setMenuOpen(false);
  }

  function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const q = (formData.get("q") as string | null)?.trim() ?? "";
    if (q) {
      closeMenu();
      navigate(`/search/?q=${encodeURIComponent(q)}`);
    }
  }

  return (
    <CompareProvider>
      <StripTrailingSlash />
      <ScrollToTop />
      <Analytics />
      <ScrollProgress />
      <a href="#main-content" className="skip-link">
        Перейти к содержимому
      </a>

      <header className={styles.headerSticky}>
        <div className={styles.masthead}>
          <div className={`container ${styles.mastheadInner}`}>
            <a href="tel:+78003505898" className={styles.mastheadLink}>
              8 800 350-58-98
            </a>
            <span className={styles.mastheadSep} aria-hidden="true">
              ·
            </span>
            <a href="mailto:sales@hoocon.ru" className={styles.mastheadLink}>
              sales@hoocon.ru
            </a>
            <span className={styles.mastheadSpacer} />
            <span className={styles.mastheadNote}>Склад в Москве · B2B</span>
          </div>
        </div>

        <div className={styles.siteHead}>
          <div className={`container ${styles.siteHeadRow}`}>
            <Link to="/" className={styles.logo} aria-label="Hoocon — на главную">
              <BrandLogo />
            </Link>

            <DesktopNav />

            <div className={styles.siteHeadActions}>
              <form
                className={styles.searchFormDesktop}
                onSubmit={handleSearch}
                role="search"
              >
                <input
                  type="search"
                  name="q"
                  className={styles.searchInput}
                  placeholder="Поиск по сайту…"
                  aria-label="Поиск по сайту"
                />
                <button type="submit" className={styles.searchButton}>
                  Найти
                </button>
              </form>

              <ThemeToggle />

              <Link to="/consultation" className={styles.ctaButton} data-brand-cta>
                Запросить КП
              </Link>

              <button
                type="button"
                className={styles.menuToggle}
                aria-expanded={menuOpen}
                aria-controls={menuId}
                aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
                onClick={() => setMenuOpen((open) => !open)}
              >
                <span className={styles.menuToggleBars} aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
              </button>
            </div>
          </div>
        </div>
      </header>

      <div
        id={menuId}
        className={menuOpen ? styles.mobilePanelOpen : styles.mobilePanel}
        hidden={!menuOpen}
        role="dialog"
        aria-modal={menuOpen}
        aria-label="Меню сайта"
      >
        <div className={styles.mobilePanelTop}>
          <span className={styles.mobilePanelBrand} aria-hidden="true">
            <BrandLogo />
          </span>
          <button
            type="button"
            className={styles.menuClose}
            aria-label="Закрыть меню"
            onClick={closeMenu}
          >
            <span className={styles.menuCloseIcon} aria-hidden="true" />
          </button>
        </div>
        <div className={`container ${styles.mobilePanelInner}`}>
          <form
            className={styles.searchFormMobile}
            onSubmit={handleSearch}
            role="search"
          >
            <input
              type="search"
              name="q"
              className={styles.searchInput}
              placeholder="Поиск по сайту…"
              aria-label="Поиск по сайту"
            />
            <button type="submit" className={styles.searchButton}>
              Найти
            </button>
          </form>

          <nav className={styles.navMobile} aria-label="Мобильное меню">
            <Link to="/catalog" className={styles.navMobileLink} onClick={closeMenu}>
              Каталог
            </Link>
            <Link to="/statyi" className={styles.navMobileLink} onClick={closeMenu}>
              Статьи
            </Link>
            <Link to="/novosti" className={styles.navMobileLink} onClick={closeMenu}>
              Новости
            </Link>
            <Link
              to="/company"
              className={styles.navMobileLink}
              onClick={closeMenu}
            >
              О компании
            </Link>
            <Link
              to="/zavod"
              className={styles.navMobileLink}
              onClick={closeMenu}
            >
              Завод · OEM напрямую
            </Link>
            <Link
              to="/gde-kupit"
              className={styles.navMobileLink}
              onClick={closeMenu}
            >
              Где купить
            </Link>
            <Link to="/kontakty" className={styles.navMobileLink} onClick={closeMenu}>
              Контакты
            </Link>
            <Link to="/faq" className={styles.navMobileLink} onClick={closeMenu}>
              Вопросы
            </Link>
            <Link
              to="/compare"
              className={styles.navMobileLink}
              onClick={closeMenu}
            >
              Сравнение
            </Link>
          </nav>

          <ThemeToggle showLabel />
        </div>
      </div>

      <main
        id="main-content"
        className={
          hideMobileCta || (isHome && heroKpVisible)
            ? `${styles.main} ${styles.mainNoStickyCta}`
            : styles.main
        }
      >
        <div className="container">
          <RouteSlideOutlet />
        </div>
      </main>

      <footer className={styles.footer}>
        <div className={`container ${styles.footerGrid}`}>
          <div className={styles.footerBrand}>
            <p className={styles.footerLogo}>
              <BrandLogo onDark alt="Hoocon" />
            </p>
            <p>
              Электроприводы для вентиляции, противопожарной безопасности и
              дымоудаления.
            </p>
            <p>Склад в Москве · поставки по РФ</p>
          </div>
          <div>
            <h2 className={styles.footerHeading}>Каталог</h2>
            <ul className={styles.footerList}>
              <li>
                <Link to="/catalog">Вся продукция</Link>
              </li>
              <li>
                <Link to="/compare">Сравнение</Link>
              </li>
              <li>
                <Link to="/replacement">Аналог Belimo</Link>
              </li>
              <li>
                <Link to="/search">Поиск</Link>
              </li>
            </ul>
          </div>
          <div>
            <h2 className={styles.footerHeading}>Компания</h2>
            <ul className={styles.footerList}>
              <li>
                <Link to="/company">О компании</Link>
              </li>
              <li>
                <Link to="/zavod">OEM · завод</Link>
              </li>
              <li>
                <Link to="/gde-kupit">Где купить</Link>
              </li>
              <li>
                <Link to="/faq">Вопросы</Link>
              </li>
              <li>
                <Link to="/statyi">Статьи</Link>
              </li>
              <li>
                <Link to="/novosti">Новости</Link>
              </li>
            </ul>
          </div>
          <div>
            <h2 className={styles.footerHeading}>Контакты</h2>
            <ul className={styles.footerList}>
              <li>
                <a href="tel:+78003505898">8 800 350-58-98</a>
              </li>
              <li>
                <a href="mailto:sales@hoocon.ru">sales@hoocon.ru</a>
              </li>
              <li>
                <Link to="/consultation">Консультация инженера</Link>
              </li>
              <li>
                <Link to="/kontakty">Все контакты</Link>
              </li>
            </ul>
          </div>
        </div>
        <div className={`container ${styles.footerBottom}`}>
          <p>
            © {new Date().getFullYear()} Hoocon · Системы вентиляции и
            кондиционирования
            <span className={styles.footerRelease}> · {releaseLabel()}</span>
          </p>
          <nav className={styles.footerLegal} aria-label="Правовая информация">
            <Link to="/privacy-policy">Обработка ПДн</Link>
            <Link to="/terms">Согласие на ПДн</Link>
            <Link to="/oferta">Оферта</Link>
            <button
              type="button"
              className={styles.footerCookieButton}
              onClick={openCookieConsentSettings}
            >
              Настройки cookie
            </button>
          </nav>
        </div>
      </footer>

      <CompareTray />

      {showMobileStickyCta ? (
        <Link
          to="/consultation"
          className={styles.mobileStickyCta}
          data-brand-cta
        >
          Запросить КП
        </Link>
      ) : null}

      <CookieConsent />
    </CompareProvider>
  );
}
