import { Form, Link, Outlet, useNavigate } from "react-router-dom";

import styles from "./Layout.module.css";

/**
 * App shell: header (logo + nav + search) + main content + footer.
 *
 * Spec: ПЛАН §6 Iter 4; docs/readiness-backend-ux.md (B2B UX, IBM Plex Sans).
 * No Cart/Wishlist icons (B2B without checkout in v1).
 */
export function Layout() {
  const navigate = useNavigate();

  function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const q = (formData.get("q") as string | null)?.trim() ?? "";
    if (q) {
      navigate(`/search/?q=${encodeURIComponent(q)}`);
    }
  }

  return (
    <>
      <header className={styles.header}>
        <div className={`container ${styles.headerInner}`}>
          <Link to="/" className={styles.logo}>
            Hoocon
          </Link>

          <nav className={styles.nav}>
            <Link to="/catalog" className={styles.navLink}>
              Каталог
            </Link>
            <Link to="/statyi" className={styles.navLink}>
              Статьи
            </Link>
            <Link to="/novosti" className={styles.navLink}>
              Новости
            </Link>
            <Link to="/o-kompanii" className={styles.navLink}>
              О компании
            </Link>
            <Link to="/kontakty" className={styles.navLink}>
              Контакты
            </Link>
          </nav>

          <Form className={styles.searchForm} onSubmit={handleSearch} role="search">
            <input
              type="search"
              name="q"
              className={styles.searchInput}
              placeholder="Поиск по каталогу и статьям"
              aria-label="Поиск"
            />
            <button type="submit" className={styles.searchButton}>
              Найти
            </button>
          </Form>
        </div>
      </header>

      <main className={styles.main}>
        <div className="container">
          <Outlet />
        </div>
      </main>

      <footer className={styles.footer}>
        <div className={`container ${styles.footerInner}`}>
          <div>
            <p>© {new Date().getFullYear()} Hoocon — электроприводы ОВК</p>
            <p>Производство и поставка приводов для вентиляции и кондиционирования.</p>
          </div>
          <div className={styles.footerContacts}>
            <p>
              <a href="mailto:sales@hoocon.ru">sales@hoocon.ru</a>
            </p>
            <p>+7 (495) 000-00-00</p>
          </div>
        </div>
      </footer>
    </>
  );
}
