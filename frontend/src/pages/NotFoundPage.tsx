import { Link, useLocation } from "react-router-dom";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import styles from "./NotFoundPage.module.css";

const NEXT_STEPS: { to: string; label: string; hint: string }[] = [
  {
    to: "/catalog",
    label: "Каталог",
    hint: "приводы и арматура по сериям",
  },
  {
    to: "/search",
    label: "Поиск",
    hint: "найти по артикулу или названию",
  },
  {
    to: "/statyi",
    label: "Статьи",
    hint: "подбор, серии, спецификации",
  },
  {
    to: "/consultation",
    label: "Консультация инженера",
    hint: "если нужна помощь с подбором",
  },
];

/**
 * 404 — short explanation, requested path, and a few clear next steps.
 * Spec: Zen — readable, no noise; B2B RFQ over checkout.
 */
export function NotFoundPage() {
  const { pathname } = useLocation();
  const showPath = Boolean(pathname && pathname !== "/");

  return (
    <div className={styles.notFound}>
      <Seo title="Страница не найдена — 404" noindex />
      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          { label: "Страница не найдена" },
        ]}
      />

      <p className={styles.code} aria-hidden>
        404
      </p>
      <h1 className={styles.title}>Страница не найдена</h1>
      <p className={styles.lead}>
        Адрес устарел, в ссылке опечатка, или такой страницы ещё нет. Ниже —
        куда обычно идут дальше.
      </p>

      {showPath ? (
        <p className={styles.path}>
          Запрошенный адрес:{" "}
          <code className={styles.pathCode}>{pathname}</code>
        </p>
      ) : null}

      <ul className={styles.nextList}>
        {NEXT_STEPS.map((item) => (
          <li key={item.to}>
            <Link to={item.to} className={styles.nextLink}>
              <span className={styles.nextLabel}>{item.label}</span>
              <span className={styles.nextHint}>{item.hint}</span>
            </Link>
          </li>
        ))}
      </ul>

      <p className={styles.homeWrap}>
        <Link to="/" className={styles.homeLink}>
          На главную
        </Link>
      </p>
    </div>
  );
}
