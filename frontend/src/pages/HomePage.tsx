import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { HomeSkeleton } from "../components/HomeSkeleton";
import { Seo } from "../components/Seo";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { softBreak } from "../utils/softBreak";
import { buildHomeJsonLd } from "../utils/jsonLd";
import styles from "./HomePage.module.css";

/** Auto-advance interval for hero background slides. */
const HERO_SLIDE_MS = 6500;

/** Soft cap for category card lead under the title. */
const CATEGORY_LEAD_MAX = 140;

/**
 * First sentence of a category description for the directions card.
 *
 * Args:
 *   description: Raw category description from the API.
 *   maxLen: Soft character cap before ellipsis.
 *
 * Returns:
 *   Plain lead text, or empty string when description is blank.
 */
function categoryLead(
  description: string,
  maxLen: number = CATEGORY_LEAD_MAX,
): string {
  const text = description.replace(/\s+/g, " ").trim();
  if (!text) {
    return "";
  }
  const first = text.split(/(?<=[.!?…])\s+/)[0] ?? text;
  if (first.length <= maxLen) {
    return first;
  }
  const cut = first.slice(0, maxLen - 1).replace(/\s+\S*$/, "");
  return `${cut || first.slice(0, maxLen - 1)}…`;
}

type DirectionImageProps = {
  apiSrc: string | null | undefined;
  className: string;
  placeholderClassName: string;
};

/** Direction card photo from the catalog API preview. */
function DirectionCardImage({
  apiSrc,
  className,
  placeholderClassName,
}: DirectionImageProps) {
  if (apiSrc) {
    return (
      <img
        className={className}
        src={apiSrc}
        alt=""
        loading="lazy"
        decoding="async"
      />
    );
  }
  return <span className={placeholderClassName} aria-hidden="true" />;
}

/** Partner logos from live hoocon.ru «Наша профессиональная среда». */
const HOME_PARTNERS = [
  {
    name: "Завод НЗВЗ",
    logo: "/home/partners/nzvz.webp",
    width: 480,
    height: 209,
  },
  {
    name: "Завод ВОК",
    logo: "/home/partners/vok.webp",
    width: 480,
    height: 206,
  },
  {
    name: "ТД Панорамавент",
    logo: "/home/partners/panoramavent.webp",
    width: 480,
    height: 207,
    href: "https://panoramavent.com",
  },
  {
    name: "АэроГрупп",
    logo: "/home/partners/aerogrupp.webp",
    width: 480,
    height: 97,
  },
] as const;

/** Reference installations — products in service on major sites. */
const HOME_PROJECTS = [
  {
    name: "Пекинское метро",
    image: "/home/projects/beijing-metro.webp",
    width: 1600,
    height: 1067,
  },
  {
    name: "АЭС Даявань",
    image: "/home/projects/dayawan-npp.webp",
    width: 1600,
    height: 1067,
  },
  {
    name: "БЦ SOHO",
    image: "/home/projects/soho-bc.webp",
    width: 1600,
    height: 1067,
  },
] as const;

/**
 * Home: brand-first hero + directions + trust anchors.
 * Spec: docs/readiness-backend-ux.md §4.3; БЗ маркетинг/UX industrial B2B.
 */
export function HomePage() {
  const { data: categoriesData, loading, error } = useAsync(() => api.categories(), []);
  const partnersRef = useRef<HTMLElement>(null);
  const partnersParallaxRef = useRef<HTMLDivElement>(null);
  const [heroSlide, setHeroSlide] = useState(0);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduceMotion.matches || HOME_PROJECTS.length < 2) {
      return;
    }
    const timer = window.setInterval(() => {
      setHeroSlide((prev) => (prev + 1) % HOME_PROJECTS.length);
    }, HERO_SLIDE_MS);
    return () => window.clearInterval(timer);
  }, [heroSlide]);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduceMotion.matches) {
      return;
    }

    /** Drift vs scroll; keep under bleed (~55% section height). */
    const PARALLAX_FACTOR = 0.18;
    /** Catch-up per frame; lower = smoother / more lag. */
    const PARALLAX_EASE = 0.05;

    let current = 0;
    let frame = 0;
    let running = false;

    const tick = () => {
      const section = partnersRef.current;
      const layer = partnersParallaxRef.current;
      if (!section || !layer) {
        running = false;
        return;
      }
      const rect = section.getBoundingClientRect();
      const viewH = window.innerHeight || 1;
      const mid = rect.top + rect.height / 2;
      const raw = (mid - viewH / 2) * PARALLAX_FACTOR;
      const maxShift = rect.height * 0.35;
      const target = Math.max(-maxShift, Math.min(maxShift, raw));
      current += (target - current) * PARALLAX_EASE;
      layer.style.transform = `translate3d(0, ${current.toFixed(2)}px, 0)`;

      if (Math.abs(target - current) > 0.12) {
        frame = requestAnimationFrame(tick);
      } else {
        current = target;
        layer.style.transform = `translate3d(0, ${current.toFixed(2)}px, 0)`;
        running = false;
      }
    };

    const onScroll = () => {
      if (!running) {
        running = true;
        frame = requestAnimationFrame(tick);
      }
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
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
          <ul className={styles.heroSlider}>
            {HOME_PROJECTS.map((project, index) => (
              <li
                key={project.name}
                className={
                  index === heroSlide
                    ? `${styles.heroSlide} ${styles.heroSlideActive}`
                    : styles.heroSlide
                }
              >
                <img
                  className={styles.heroSlideImg}
                  src={project.image}
                  alt=""
                  width={project.width}
                  height={project.height}
                  loading={index === 0 ? "eager" : "lazy"}
                  decoding="async"
                  fetchPriority={index === 0 ? "high" : "auto"}
                />
              </li>
            ))}
          </ul>
          <div className={styles.heroShade} />
        </div>

        <div className={styles.heroBrand}>
          <p id="hero-brand" className={styles.brand}>
            HOOCON
          </p>
          <h1 className={styles.heroTitle}>Электроприводы для систем ОВК</h1>
          <p className={styles.heroLead}>
            Подбор по ТТХ, паспорта, аналоги Belimo. Склад в Москве — отгрузка по
            РФ. КП по запросу.
          </p>
          <div className={styles.heroActions}>
            <Link to="/catalog" className={styles.ctaPrimary}>
              Смотреть каталог
            </Link>
            <Link to="/consultation" className={styles.ctaSecondary}>
              Запросить КП
            </Link>
          </div>
        </div>

        <div className={styles.heroSliderUi}>
          <p className={styles.heroSlideCaption} aria-live="polite">
            {HOME_PROJECTS[heroSlide]?.name}
          </p>
          <div className={styles.heroDots} role="tablist" aria-label="Объекты">
            {HOME_PROJECTS.map((project, index) => (
              <button
                key={project.name}
                type="button"
                role="tab"
                aria-selected={index === heroSlide}
                aria-label={project.name}
                className={
                  index === heroSlide
                    ? `${styles.heroDot} ${styles.heroDotActive}`
                    : styles.heroDot
                }
                onClick={() => setHeroSlide(index)}
              />
            ))}
          </div>
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

      <section
        className={styles.directions}
        aria-labelledby="directions-heading"
      >
        <div className={styles.directionsInner}>
          <div className={styles.sectionHead}>
            <h2 id="directions-heading">Направления продукции</h2>
            <p className={styles.sectionLead}>
              Выберите семейство по задаче: воздушные клапаны, противопожарные
              системы, дымоудаление или шаровые краны.
            </p>
          </div>
          {loading && <HomeSkeleton />}
          {error && <p className={styles.status}>Ошибка загрузки категорий.</p>}
          {categoriesData && (
            <div className={styles.directionGrid}>
              {categoriesData.results.map((cat, index) => {
                const lead = categoryLead(cat.description ?? "");
                return (
                  <Link
                    key={cat.slug}
                    to={`/catalog?category=${encodeURIComponent(cat.slug)}`}
                    className={styles.directionBlock}
                    style={{ animationDelay: `${0.06 + index * 0.05}s` }}
                  >
                    <span className={styles.directionMedia}>
                      <DirectionCardImage
                        apiSrc={cat.image?.image}
                        className={styles.directionImage}
                        placeholderClassName={styles.directionImagePlaceholder}
                      />
                    </span>
                    <span className={styles.directionBody}>
                      <span className={styles.directionName}>
                        {softBreak(cat.name)}
                      </span>
                      {lead ? (
                        <span className={styles.directionDesc}>{lead}</span>
                      ) : null}
                      <span className={styles.directionMore}>В каталог →</span>
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
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

      <section
        ref={partnersRef}
        className={styles.partners}
        aria-labelledby="partners-heading"
      >
        <div className={styles.partnersBackdrop} aria-hidden="true">
          <div ref={partnersParallaxRef} className={styles.partnersParallax}>
            <img
              className={styles.partnersParallaxImg}
              src="/home/partners-bg.webp"
              alt=""
              width={1920}
              height={1280}
              loading="lazy"
              decoding="async"
            />
          </div>
          <div className={styles.partnersShade} />
        </div>
        <div className={styles.partnersInner}>
          <div className={styles.partnersHead}>
            <h2 id="partners-heading">Наша профессиональная среда</h2>
            <p className={styles.partnersLead}>
              Производители и дистрибьюторы, с которыми работаем по проектам ОВК.
              Полный список точек продаж — на странице{" "}
              <Link to="/gde-kupit">где купить</Link>.
            </p>
          </div>
          <ul className={styles.partnerLogos}>
            {HOME_PARTNERS.map((partner) => {
              const logo = (
                <img
                  className={styles.partnerLogoImg}
                  src={partner.logo}
                  alt={partner.name}
                  width={partner.width}
                  height={partner.height}
                  loading="lazy"
                  decoding="async"
                />
              );
              return (
                <li key={partner.name} className={styles.partnerLogoItem}>
                  {partner.href ? (
                    <a
                      href={partner.href}
                      className={styles.partnerLogoLink}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      aria-label={partner.name}
                    >
                      {logo}
                    </a>
                  ) : (
                    logo
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      <section className={styles.delivery} aria-labelledby="delivery-heading">
        <div className={styles.deliveryInner}>
          <div className={styles.deliveryMedia}>
            <img
              className={styles.deliveryImg}
              src="/home/delivery.webp"
              alt=""
              width={1000}
              height={562}
              loading="lazy"
              decoding="async"
            />
          </div>
          <div className={styles.deliveryCopy}>
            <h2 id="delivery-heading">
              Быстрая доставка приводов по всей России
            </h2>
            <p>
              Доставляем электроприводы по Москве и всем регионам РФ. По Москве —
              курьером, в регионы — любой удобной транспортной компанией. При
              оплате до 12:00 возможна срочная отгрузка в тот же день; в
              остальных случаях отправим на следующий рабочий день.
            </p>
            <Link to="/consultation" className={styles.deliveryCta}>
              Запросить КП
            </Link>
          </div>
        </div>
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
