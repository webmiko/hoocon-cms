import styles from "./HomeSkeleton.module.css";

export function HomeSkeleton() {
  return (
    <div className={styles.homeSkeleton} aria-busy="true" aria-label="Загрузка главной страницы">
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <span className={styles.brand} />
          <span className={styles.heroTitle} />
          <span className={styles.heroLead} />
          <span className={styles.heroLeadShort} />
          <div className={styles.heroActions}>
            <span className={styles.ctaPrimary} />
            <span className={styles.ctaSecondary} />
          </div>
        </div>
      </section>

      <div className={styles.trust}>
        <span className={styles.trustItem} />
        <span className={styles.trustItem} />
        <span className={styles.trustItem} />
        <span className={styles.trustItem} />
      </div>

      <section className={styles.section}>
        <span className={styles.sectionTitle} />
        <span className={styles.sectionLead} />
        <div className={styles.directionGrid}>
          <span className={styles.directionCard} />
          <span className={styles.directionCard} />
          <span className={styles.directionCard} />
          <span className={styles.directionCard} />
        </div>
      </section>
    </div>
  );
}
