import { Link } from "react-router-dom";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import styles from "./NotFoundPage.module.css";

/** 404 page — shown when no route matches. */
export function NotFoundPage() {
  return (
    <div className={styles.notFound}>
      <Seo title="Страница не найдена — 404" noindex />
      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          { label: "Страница не найдена" },
        ]}
      />
      <h1>404</h1>
      <p>Страница не найдена.</p>
      <Link to="/" className={styles.link}>
        На главную
      </Link>
    </div>
  );
}
