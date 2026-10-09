import styles from "./LoadMore.module.css";

type LoadMoreProps = {
  hasNext: boolean;
  loading: boolean;
  error: string | null;
  onLoadMore: () => void;
};

/** «Показать ещё» under a paged list; renders nothing on the last page. */
export function LoadMore({ hasNext, loading, error, onLoadMore }: LoadMoreProps) {
  if (!hasNext && !error) return null;
  return (
    <div className={styles.footer}>
      {hasNext ? (
        <button type="button" className={styles.button} disabled={loading} onClick={onLoadMore}>
          {loading ? "Загрузка…" : "Показать ещё"}
        </button>
      ) : null}
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
