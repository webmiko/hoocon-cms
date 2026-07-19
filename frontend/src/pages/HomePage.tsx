import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import styles from "./HomePage.module.css";

/**
 * Home page: hero + featured categories + CTA to catalog.
 * Spec: ПЛАН §6 Iter 4; docs/readiness-backend-ux.md.
 */
export function HomePage() {
  const { data: categoriesData, loading, error } = useAsync(() => api.categories(), []);

  return (
    <div className={styles.home}>
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <h1>Электроприводы ОВК от Hoocon</h1>
          <p className={styles.heroSubtitle}>
            Производим приводы для воздушных клапанов, противопожарных систем и
            шаровых кранов. Подбор по ТТХ, паспорта, аналоги Belimo.
          </p>
          <div className={styles.heroActions}>
            <Link to="/catalog" className={styles.ctaPrimary}>
              Перейти в каталог
            </Link>
            <Link to="/o-kompanii" className={styles.ctaSecondary}>
              О компании
            </Link>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <h2>Категории продукции</h2>
        {loading && <p>Загрузка…</p>}
        {error && <p>Ошибка загрузки категорий.</p>}
        {categoriesData && (
          <div className={styles.categoryGrid}>
            {categoriesData.results.map((cat) => (
              <Link
                key={cat.slug}
                to={`/catalog?category=${encodeURIComponent(cat.slug)}`}
                className={styles.categoryCard}
              >
                <h3>{cat.name}</h3>
                {cat.description && <p>{cat.description}</p>}
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <h2>Как мы работаем</h2>
        <div className={styles.featuresGrid}>
          <div className={styles.featureCard}>
            <h3>Подбор по ТТХ</h3>
            <p>Фильтры по моменту, напряжению, типу пружины — найдите нужную модель за минуту.</p>
          </div>
          <div className={styles.featureCard}>
            <h3>Паспорта и сертификаты</h3>
            <p>PDF-документы на каждый SKU доступны для скачивания в карточке товара.</p>
          </div>
          <div className={styles.featureCard}>
            <h3>Аналоги Belimo</h3>
            <p>Подберём замену по артикулу Belimo. Запросите подбор через форму на сайте.</p>
          </div>
          <div className={styles.featureCard}>
            <h3>Запрос КП</h3>
            <p>Цены — по запросу. Отправьте спецификацию, менеджер ответит с коммерческим предложением.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
