import { Link } from "react-router-dom";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import { buildBreadcrumbJsonLd } from "../utils/jsonLd";
import styles from "./WhereToBuyPage.module.css";

const PHONE = "8 800 350-58-98";
const EMAIL_SALES = "sales@hoocon.ru";

interface Partner {
  name: string;
  city: string;
  lines: string[];
  links?: Array<{ href: string; label: string; external?: boolean }>;
}

const PARTNERS: Partner[] = [
  {
    name: "«ТД Панорамавент»",
    city: "Москва",
    lines: [
      "ул. Производственная, д. 11, стр. 6",
      "+7 (495) 380-06-76",
      "info@panoramavent.ru",
      "Пн–Пт 9:00–19:00",
    ],
  },
  {
    name: "ООО «Аэро Групп»",
    city: "Москва",
    lines: [
      "ул. Электрозаводская, д. 24, офис 306",
      "+7 (495) 780-31-41",
      "office@aerostarmsk.ru",
      "Telegram @aerogrupp",
      "Пн–Пт 9:00–18:00",
    ],
    links: [
      {
        href: "https://www.aerogrupp.ru",
        label: "aerogrupp.ru",
        external: true,
      },
    ],
  },
  {
    name: "ООО «Смарт Альянс»",
    city: "Санкт-Петербург",
    lines: [
      "Офис: ул. Мельничная, д. 16, корп. 1, этаж 3",
      "Склад: ул. Мельничная, д. 11",
      "8 (800) 333-28-19",
      "Пн–Пт 10:00–17:00",
    ],
    links: [
      {
        href: "https://www.hoocon.spb.ru",
        label: "hoocon.spb.ru",
        external: true,
      },
    ],
  },
  {
    name: "ООО «РосАвтоматизация»",
    city: "Минск",
    lines: [
      "ул. Мележа, 1",
      "+375 29 697-11-02",
      "mail.sensorica.by@gmail.com",
    ],
    links: [
      { href: "https://www.hoocon.by", label: "hoocon.by", external: true },
    ],
  },
];

/**
 * «Где купить» — партнёры карточками, OEM-полоса на всю ширину внизу.
 */
export function WhereToBuyPage() {
  const jsonLd = [
    buildBreadcrumbJsonLd([
      { name: "Главная", path: "/" },
      { name: "Где купить", path: "/gde-kupit" },
    ]),
  ];

  return (
    <div className={styles.page}>
      <Seo
        title="Где купить продукцию Hoocon"
        description={
          "Партнёры и прямые поставки электроприводов Hoocon: Москва, " +
          "Санкт-Петербург, Минск. OEM напрямую с завода — /zavod."
        }
        path="/gde-kupit"
        jsonLd={jsonLd}
      />

      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          { label: "Где купить" },
        ]}
      />

      <header className={styles.header}>
        <h1 className={styles.title}>Где купить продукцию Hoocon</h1>
        <p className={styles.lead}>
          Юридические лица могут заказать приводы напрямую у ООО «Хогон»
          (склад в Московской области) или у региональных партнёров. Физическим
          лицам удобнее обратиться к партнёру в своём городе.
        </p>
      </header>

      <section className={styles.section} aria-labelledby="direct-heading">
        <h2 id="direct-heading" className={styles.sectionTitle}>
          Прямые поставки (B2B)
        </h2>
        <article className={`${styles.card} ${styles.cardFeatured}`}>
          <p className={styles.cardLead}>
            Склад в Московской области. КП под спецификацию — ответ до 2 рабочих
            часов.
          </p>
          <ul className={styles.cardMeta}>
            <li>
              <a href={`tel:+78003505898`}>{PHONE}</a>
            </li>
            <li>
              <a href={`mailto:${EMAIL_SALES}`}>{EMAIL_SALES}</a>
            </li>
          </ul>
          <Link to="/consultation" className={styles.cardCta} data-brand-cta>
            Запросить КП
          </Link>
        </article>
      </section>

      <section className={styles.section} aria-labelledby="partners-heading">
        <h2 id="partners-heading" className={styles.sectionTitle}>
          Партнёры
        </h2>
        <div className={styles.grid}>
          {PARTNERS.map((partner) => (
            <article key={partner.name} className={styles.card}>
              <p className={styles.cardCity}>{partner.city}</p>
              <h3 className={styles.cardTitle}>{partner.name}</h3>
              <ul className={styles.cardMeta}>
                {partner.lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
                {partner.links?.map((link) => (
                  <li key={link.href}>
                    {link.external ? (
                      <a
                        href={link.href}
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        {link.label}
                      </a>
                    ) : (
                      <Link to={link.href}>{link.label}</Link>
                    )}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.oemBand} aria-labelledby="oem-heading">
        <div className={styles.oemInner}>
          <article className={`${styles.card} ${styles.cardOem}`}>
            <p className={styles.oemEyebrow}>Завод · OEM</p>
            <h2 id="oem-heading" className={styles.oemTitle}>
              Приводы под вашим брендом — напрямую с завода
            </h2>
            <p className={styles.oemText}>
              Ningbo Hoocon Automation (Цыси, Китай): контракт, образцы и серия
              без посредников. CE · UL · EAC · ISO&nbsp;9001. Контакты завода,
              платформы и условия OEM — на отдельной странице.
            </p>
            <Link to="/zavod" className={styles.oemCta} data-brand-cta>
              Страница завода →
            </Link>
          </article>
        </div>
      </section>
    </div>
  );
}
