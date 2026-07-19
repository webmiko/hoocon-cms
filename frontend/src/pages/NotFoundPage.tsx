import { Link } from "react-router-dom";

import styles from "./NotFoundPage.module.css";

/** 404 page — shown when no route matches. */
export function NotFoundPage() {
  return (
    <div className={styles.notFound}>
      <h1>404</h1>
      <p>Страница не найдена.</p>
      <Link to="/" className={styles.link}>
        На главную
      </Link>
    </div>
  );
}
