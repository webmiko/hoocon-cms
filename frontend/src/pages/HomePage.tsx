import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { DirectionsCategoryGrid } from "../components/DirectionsCategoryGrid";
import { HomeCasesCarousel } from "../components/HomeCasesCarousel";
import { HomeSkeleton } from "../components/HomeSkeleton";
import { NovinkiCarousel } from "../components/NovinkiCarousel";
import { Seo } from "../components/Seo";
import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
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
const HOME_PARTNERS: ReadonlyArray<{
  name: string;
  logo: string;
  width: number;
  height: number;
  href?: string;
}> = [
  {
    name: "Завод НЗВЗ",
    logo: "/home/partners/nzvz.webp",
    width: 260,
    height: 113,
  },
  {
    name: "Завод ВОК",
    logo: "/home/partners/vok.webp",
    width: 260,
    height: 112,
  },
  {
    name: "ТД Панорамавент",
    logo: "/home/partners/panoramavent.webp",
    width: 260,
    height: 112,
    href: "https://panoramavent.com",
  },
  {
    name: "АэроГрупп",
    logo: "/home/partners/aerogrupp.webp",
    width: 260,
    height: 53,
  },
];

/** Reference installations — products in service on major sites (~960w for LCP). */
const HOME_PROJECTS = [
  {
    name: "Пекинское метро",
    lead:
      "Приводы на системах вентиляции метрополитена — круглосуточная нагрузка "
      + "и жёсткие требования к надёжности.",
    image: "/home/projects/beijing-metro.webp",
    width: 960,
    height: 640,
  },
  {
    name: "АЭС Даявань, Шэньчжэнь",
    lead:
      "Объекты атомной энергетики: сертифицированные приводы для вентиляционных "
      + "и противопожарных контуров.",
    image: "/home/projects/dayawan-npp.webp",
    width: 960,
    height: 640,
  },
  {
    name: "БЦ SOHO",
    lead:
      "Коммерческие здания: приводы воздушных клапанов и климат-систем в плотной "
      + "городской застройке.",
    image: "/home/projects/soho-bc.webp",
    width: 960,
    height: 640,
  },
] as const;

/**
 * Home: brand-first hero + directions + trust anchors.
 * Spec: docs/readiness-backend-ux.md §4.3; БЗ маркетинг/UX industrial B2B.
 */
export function HomePage() {
  const { data: categoriesData, loading, error } = useAsync(() => api.categories());
  const { data: novinkiData, loading: novinkiLoading } = useAsync(
    () => api.skus({ new: "1", page_size: "8" }),
    0,
    "home:novinki",
  );
  const partnersRef = useRef<HTMLElement>(null);
  const partnersParallaxRef = useRef<HTMLDivElement>(null);
  const [heroSlide, setHeroSlide] = useState(0);
  /** Only decode slides once shown — keeps inactive hero WebPs off first paint. */
  const [loadedHeroSlides, setLoadedHeroSlides] = useState<ReadonlySet<number>>(
    () => new Set([0]),
  );

  // Adjust loaded set during render (same pattern as Layout menuRoute).
  if (!loadedHeroSlides.has(heroSlide)) {
    const next = new Set(loadedHeroSlides);
    next.add(heroSlide);
    setLoadedHeroSlides(next);
  }

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
    /** Cached geometry — avoid getBoundingClientRect on every scroll frame. */
    let sectionTop = 0;
    let sectionHeight = 1;

    const measure = () => {
      const section = partnersRef.current;
      if (!section) {
        return;
      }
      const rect = section.getBoundingClientRect();
      sectionTop = rect.top + window.scrollY;
      sectionHeight = rect.height || 1;
    };

    const tick = () => {
      const layer = partnersParallaxRef.current;
      if (!layer) {
        running = false;
        return;
      }
      const viewH = window.innerHeight || 1;
      const mid = sectionTop - window.scrollY + sectionHeight / 2;
      const raw = (mid - viewH / 2) * PARALLAX_FACTOR;
      const maxShift = sectionHeight * 0.35;
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

    const onResize = () => {
      measure();
      onScroll();
    };

    measure();
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return (
    <div className={styles.home}>
      <Seo
        title="Электроприводы для вентиляции и кондиционирования Hoocon — каталог, подбор, аналоги Belimo"
        description={
          "Электроприводы для вентиляции, кондиционирования и "
          + "противопожарных систем. Каталог, фильтры по характеристикам, паспорта, аналоги "
          + "Belimo, запрос КП."
        }
        path="/"
        preloadImage={HOME_PROJECTS[0].image}
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
                {loadedHeroSlides.has(index) ? (
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
                ) : null}
              </li>
            ))}
          </ul>
          <div className={styles.heroShade} />
        </div>

        <div className={styles.heroBrand}>
          <p id="hero-brand" className={styles.brand}>
            HOOCON
          </p>
          <h1 className={styles.heroTitle}>
            Электроприводы для вентиляции и кондиционирования
          </h1>
          <p className={styles.heroLead}>
            Подбор по техническим характеристикам, паспорта, аналоги Belimo.
            Склад в Москве — отгрузка по РФ. КП по запросу.
          </p>
          <div className={styles.heroActions}>
            <Link to="/catalog" className={styles.ctaPrimary} data-brand-cta>
              Смотреть каталог
            </Link>
            <Link
              to="/consultation"
              className={styles.ctaSecondary}
              id="hero-kp-cta"
              data-on-dark-cta
            >
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

      <section className={styles.section} aria-labelledby="cases-heading">
        <div className={styles.sectionHead}>
          <h2 id="cases-heading">На объектах</h2>
          <p className={styles.sectionLead}>
            Среда, где работают приводы Hoocon: метро, энергетика, коммерческие
            здания. Детали поставки — в ответе на запрос КП.
          </p>
        </div>
        <HomeCasesCarousel projects={HOME_PROJECTS} />
      </section>

      <section
        className={styles.directions}
        aria-labelledby="directions-heading"
      >
        <div className={styles.directionsInner}>
          <div className={styles.sectionHead}>
            <h2 id="directions-heading">Направления продукции</h2>
            <p className={styles.sectionLead}>
              Выберите линейку продукции по задаче: воздушные клапаны,
              противопожарные системы, дымоудаление или шаровые краны.
            </p>
          </div>
          {loading && <HomeSkeleton />}
          {error && <p className={styles.status}>Ошибка загрузки категорий.</p>}
          {categoriesData && (
            <DirectionsCategoryGrid
              categories={categoriesData.results}
              categoryLead={categoryLead}
              DirectionCardImage={DirectionCardImage}
            />
          )}
        </div>
      </section>

      {(novinkiLoading || (novinkiData?.results?.length ?? 0) > 0) && (
        <section
          className={styles.section}
          aria-labelledby="novinki-heading"
        >
          <div className={styles.sectionHead}>
            <h2 id="novinki-heading">Новинки</h2>
            <p className={styles.sectionLead}>
              Линейки, недавно появившиеся в каталоге. Полный список — с
              фильтром «Новинки».
            </p>
          </div>
          {novinkiLoading ? (
            <p className={styles.status}>Загрузка новинок…</p>
          ) : (
            <>
              <NovinkiCarousel skus={novinkiData?.results ?? []} />
              <p className={styles.novinkiMore}>
                <Link to="/catalog?new=1">Все новинки в каталоге</Link>
              </p>
            </>
          )}
        </section>
      )}

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
              <h3>Подбор по характеристикам</h3>
              <p>Фильтры по моменту, напряжению, типу пружины и артикулу.</p>
            </div>
          </li>
          <li>
            <span className={styles.stepNum}>2</span>
            <div>
              <h3>Паспорта и сертификаты</h3>
              <p>PDF в карточке модели — для согласования и проектной документации.</p>
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
            <h2 id="partners-heading">Партнёры по проектам ОВК</h2>
            <p className={styles.partnersLead}>
              Производители и дистрибьюторы, с которыми работаем по проектам
              вентиляции и кондиционирования. Полный список точек продаж — на
              странице{" "}
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
              width={720}
              height={405}
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
            <Link to="/consultation" className={styles.deliveryCta} data-brand-cta>
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
              нагреве). DA — для общеобменной вентиляции. Для огнезадерживающих
              клапанов используйте серию SA.
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
              Подберите модель в каталоге или опишите задачу —{" "}
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
