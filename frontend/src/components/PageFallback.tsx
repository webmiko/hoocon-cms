import { serverCrawlIsShowing } from "../utils/serverCrawl";
import styles from "./PageFallback.module.css";

/**
 * Minimal route-level Suspense fallback (lazy page chunks).
 * Avoids a heavy skeleton on every navigation.
 * The «Загрузка…» string is omitted while the server article is still the
 * visible page — Yandex was copying that string into the snippet.
 */
export function PageFallback() {
  return (
    <div className={styles.root} role="status" aria-live="polite">
      {serverCrawlIsShowing() ? null : <span className={styles.srOnly}>Загрузка…</span>}
      <span className={styles.bar} aria-hidden="true" />
    </div>
  );
}
