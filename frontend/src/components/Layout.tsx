import { useEffect, useId, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { CompareProvider } from "../compare/CompareContext";
import { CompareTray } from "./CompareTray";
import { CookieConsent } from "./CookieConsent";
import { Analytics } from "./Analytics";
import { DesktopNav } from "./DesktopNav";
import { ScrollProgress } from "./ScrollProgress";
import { ScrollToTop } from "./ScrollToTop";
import { StripTrailingSlash } from "./StripTrailingSlash";
import { ThemeToggle } from "./ThemeToggle";
import { openCookieConsentSettings } from "../utils/cookieConsent";
import styles from "./Layout.module.css";

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

  // Close mobile menu when the route changes (adjust state during render).
  if (menuRoute !== routeKey) {
    setMenuRoute(routeKey);
    setMenuOpen(false);
  }

  useEffect(() => {
    const root = document.documentElement;
    if (hideMobileCta) {
      root.dataset.stickyCta = "off";
    } else {
      delete root.dataset.stickyCta;
    }
    return () => {
      delete root.dataset.stickyCta;
    };
  }, [hideMobileCta]);

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
              HOOCON
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

              <Link to="/consultation" className={styles.ctaButton}>
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
            HOOCON
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
            <Link
              to="/consultation"
              className={styles.navMobileCta}
              onClick={closeMenu}
            >
              Запросить КП
            </Link>
          </nav>

          <ThemeToggle showLabel />
        </div>
      </div>

      <main
        id="main-content"
        className={
          hideMobileCta ? `${styles.main} ${styles.mainNoStickyCta}` : styles.main
        }
      >
        <div className="container">
          <Outlet />
        </div>
      </main>

      <footer className={styles.footer}>
        <div className={`container ${styles.footerGrid}`}>
          <div className={styles.footerBrand}>
            <p className={styles.footerLogo}>HOOCON</p>
            <p>Электроприводы для вентиляции, ПБ и дымоудаления.</p>
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
          <p>© {new Date().getFullYear()} Hoocon · Управление системами ОВК</p>
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

      {!hideMobileCta ? (
        <Link to="/consultation" className={styles.mobileStickyCta}>
          Запросить КП
        </Link>
      ) : null}

      <CookieConsent />
    </CompareProvider>
  );
}
