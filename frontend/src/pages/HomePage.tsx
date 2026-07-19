import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import { HomeSkeleton } from "../components/HomeSkeleton";
import { Seo } from "../components/Seo";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { softBreak } from "../utils/softBreak";
import { buildHomeJsonLd } from "../utils/jsonLd";
import styles from "./HomePage.module.css";

/** Hero loop playback — slower than source for softer fades. */
const HERO_VIDEO_PLAYBACK_RATE = 0.55;

/**
 * Home: brand-first hero + directions + trust anchors.
 * Spec: docs/readiness-backend-ux.md §4.3; БЗ маркетинг/UX industrial B2B.
 */
export function HomePage() {
  const { data: categoriesData, loading, error } = useAsync(() => api.categories(), []);
  const heroVideoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = heroVideoRef.current;
    if (!video) {
      return;
    }
    const applyRate = () => {
      video.playbackRate = HERO_VIDEO_PLAYBACK_RATE;
    };
    applyRate();
    video.addEventListener("play", applyRate);
    video.addEventListener("loadedmetadata", applyRate);
    return () => {
      video.removeEventListener("play", applyRate);
      video.removeEventListener("loadedmetadata", applyRate);
    };
  }, []);

  return (
    <div className={styles.home}>
      <Seo
        title="Электроприводы ОВК Hoocon — каталог, подбор, аналоги Belimo"
        description="Производство электроприводов для вентиляции, кондиционирования и противопожарных систем. Каталог, фильтры по ТТХ, паспорта, аналоги Belimo, запрос КП."
        path="/"
        jsonLd={buildHomeJsonLd()}
      />

      <section className={styles.hero} aria-labelledby="hero-brand">
        <div className={styles.heroMedia} aria-hidden="true">
          <video
            ref={heroVideoRef}
            className={styles.heroVideo}
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            poster="/hero/hvac-vent-poster.jpg"
          >
            <source src="/hero/hvac-vent.mp4" type="video/mp4" />
          </video>
          <div className={styles.heroShade} />
        </div>
        <div className={styles.heroInner}>
          <p id="hero-brand" className={styles.brand}>
            HOOCON
          </p>
          <h1 className={styles.heroTitle}>Электроприводы для систем ОВК</h1>
          <p className={styles.heroLead}>
            Для проектировщиков, снабжения и монтажных организаций: подбор по ТТХ,
            паспорта и сертификаты, замена Belimo. Коммерческое предложение по
            запросу — склад в Москве, отгрузка по РФ.
          </p>
          <div className={styles.heroActions}>
            <Link to="/catalog" className={styles.ctaPrimary}>
              Смотреть каталог
            </Link>
            <Link to="/consultation" className={styles.ctaSecondary}>
              Запросить КП
            </Link>
          </div>
          <p className={styles.heroNote}>
            После заявки ответим до 2 рабочих часов — с расчётом или уточняющими
            вопросами по спецификации.
          </p>
        </div>
      </section>

      <section className={styles.trust} aria-label="Преимущества">
        <div className={styles.trustItem}>
          <strong>Склад Москва</strong>
          <span>Отгрузка по РФ</span>
        </div>
        <div className={styles.trustItem}>
          <strong>CE · UL · EAC</strong>
          <span>Сертификаты в карточке</span>
        </div>
        <div className={styles.trustItem}>
          <strong>Ответ до 2 раб. ч.</strong>
          <span>По заявке на КП</span>
        </div>
        <div className={styles.trustItem}>
          <strong>Аналоги Belimo</strong>
          <span>Подбор замены</span>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2>Направления продукции</h2>
          <p className={styles.sectionLead}>
            Выберите семейство по задаче: воздушные клапаны, противопожарные
            системы, дымоудаление или шаровые краны.
          </p>
        </div>
      {loading && <HomeSkeleton />}
      {error && <p className={styles.status}>Ошибка загрузки категорий.</p>}
      {categoriesData && (
          <div className={styles.directionGrid}>
            {categoriesData.results.map((cat) => (
              <Link
                key={cat.slug}
                to={`/catalog?category=${encodeURIComponent(cat.slug)}`}
                className={styles.directionLink}
              >
                {cat.image?.image ? (
                  <img
                    className={styles.directionImage}
                    src={cat.image.image}
                    alt=""
                    loading="lazy"
                    decoding="async"
                  />
                ) : (
                  <span
                    className={styles.directionImagePlaceholder}
                    aria-hidden="true"
                  />
                )}
                <span className={styles.directionBody}>
                  <span className={styles.directionName}>
                    {softBreak(cat.name)}
                  </span>
                  <span className={styles.directionArrow} aria-hidden="true">
                    →
                  </span>
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2>Инженерный путь</h2>
          <p className={styles.sectionLead}>
            Параметр → документ → заявка. Цены не публикуем: готовим КП под вашу
            спецификацию и объём.
          </p>
        </div>
        <ol className={styles.steps}>
          <li>
            <span className={styles.stepNum}>1</span>
            <div>
              <h3>Подбор по ТТХ</h3>
              <p>Фильтры по моменту, напряжению, типу пружины и артикулу.</p>
            </div>
          </li>
          <li>
            <span className={styles.stepNum}>2</span>
            <div>
              <h3>Паспорта и сертификаты</h3>
              <p>PDF в карточке SKU — для согласования и проектной документации.</p>
            </div>
          </li>
          <li>
            <span className={styles.stepNum}>3</span>
            <div>
              <h3>Запрос КП</h3>
              <p>
                Менеджер подготовит КП под спецификацию — ответ до 2 рабочих часов.
              </p>
            </div>
          </li>
        </ol>
      </section>

      <section className={styles.section} aria-labelledby="faq-heading">
        <div className={styles.sectionHead}>
          <h2 id="faq-heading">Частые вопросы</h2>
          <p className={styles.sectionLead}>
            Краткие ответы для подбора и замены. Полный список — на странице{" "}
            <Link to="/faq">вопросов</Link>.
          </p>
        </div>
        <div className={styles.faqList}>
          <details className={styles.faqItem}>
            <summary>Можно ли заменить SA10FU230-DS на DA10FU230-DS?</summary>
            <p>
              Нет. SA — для огнезадерживающих клапанов (пружина ≤ 25 с, работа при
              нагреве). DA — для общеобменной вентиляции. Для ОЗК используйте
              серию SA.
            </p>
          </details>
          <details className={styles.faqItem}>
            <summary>Как оценить нужный крутящий момент?</summary>
            <p>
              Учитывайте давление, тип заслонки и среду. Ориентир:
              M ≈ (D³ × P × k) / C. Для проекта сверяйте таблицы заслонки и
              паспорт привода в каталоге.
            </p>
          </details>
          <details className={styles.faqItem}>
            <summary>Как заказать и получить КП?</summary>
            <p>
              Подберите SKU в каталоге или опишите задачу —{" "}
              <Link to="/consultation">заявка на консультацию</Link>. Ответ до 2
              рабочих часов. Партнёры:{" "}
              <Link to="/gde-kupit">где купить</Link>.
            </p>
          </details>
        </div>
      </section>
    </div>
  );
}
