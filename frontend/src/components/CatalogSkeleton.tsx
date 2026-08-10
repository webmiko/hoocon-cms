import styles from "./CatalogSkeleton.module.css";

export function CatalogSkeleton() {
  return (
    <div className={styles.catalogSkeleton} aria-busy="true" aria-label="Загрузка каталога">
      <aside className={styles.sidebar}>
        <span className={styles.sidebarTitle} />
        <div className={styles.facetGroup}>
          <span className={styles.facetLabel} />
          <div className={styles.facetChips}>
            <span className={styles.facetChip} />
            <span className={styles.facetChip} />
            <span className={styles.facetChip} />
            <span className={styles.facetChip} />
            <span className={styles.facetChip} />
          </div>
        </div>
        <div className={styles.facetGroup}>
          <span className={styles.facetLabel} />
          <div className={styles.facetChips}>
            <span className={styles.facetChip} />
            <span className={styles.facetChip} />
            <span className={styles.facetChip} />
          </div>
        </div>
      </aside>

      <div className={styles.main}>
        <div className={styles.toolbar}>
          <span className={styles.toolbarText} />
          <span className={styles.toolbarSort} />
        </div>
        <div className={styles.grid}>
          <span className={styles.card} />
          <span className={styles.card} />
          <span className={styles.card} />
          <span className={styles.card} />
          <span className={styles.card} />
          <span className={styles.card} />
        </div>
        <div className={styles.pagination}>
          <span className={styles.pageButton} />
          <span className={styles.pageButton} />
          <span className={styles.pageButton} />
        </div>
      </div>
    </div>
  );
}
