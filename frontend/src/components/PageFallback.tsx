import styles from "./PageFallback.module.css";

/**
 * Minimal route-level Suspense fallback (lazy page chunks).
 * Avoids a heavy skeleton on every navigation.
 */
export function PageFallback() {
  return (
    <div className={styles.root} role="status" aria-live="polite">
      <span className={styles.srOnly}>Загрузка…</span>
      <span className={styles.bar} aria-hidden="true" />
    </div>
  );
}
