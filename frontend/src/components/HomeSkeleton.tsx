import styles from "./HomeSkeleton.module.css";

/** Loading placeholders for the home directions block grid. */
export function HomeSkeleton() {
  return (
    <div
      className={styles.directionGrid}
      aria-busy="true"
      aria-label="Загрузка направлений продукции"
    >
      <span className={styles.directionCard} />
      <span className={styles.directionCard} />
      <span className={styles.directionCard} />
      <span className={styles.directionCard} />
      <span className={styles.directionCard} />
      <span className={styles.directionCard} />
    </div>
  );
}
