import { Link } from "react-router-dom";

import "@fontsource/montserrat/cyrillic-400.css";
import "@fontsource/montserrat/latin-400.css";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { Seo } from "../components/Seo";
import {
  formatStaffPhone,
  mailHref,
  staffPhoneHref,
  STAFF_CARDS,
  type StaffCard,
} from "../content/staffCards";
import { buildBreadcrumbJsonLd } from "../utils/jsonLd";
import styles from "./TeamPage.module.css";

const LEAD =
  "Прямые контакты сотрудников ООО «Хогон»: поставка, регионы и бренд. На визитке телефон, почта и QR, чтобы сохранить человека в адресную книгу.";

/**
 * Team section in the site shell. Each person can be called or mailed here;
 * the card link opens the full visiting card.
 */
export function TeamPage() {
  return (
    <div className={styles.page}>
      <Seo
        title="Команда"
        description="Сотрудники ООО «Хогон»: продажи, регионы и бренд. Телефон, почта и визитка."
        path="/komanda"
        noindex
        jsonLd={buildBreadcrumbJsonLd([
          { name: "Главная", path: "/" },
          { name: "Команда", path: "/komanda" },
        ])}
      />
      <Breadcrumbs items={[{ label: "Главная", to: "/" }, { label: "Команда" }]} />
      <header className={styles.header}>
        <p className={styles.kicker}>ООО «Хогон»</p>
        <h1 className={styles.title}>Команда</h1>
        <p className={styles.lead}>{LEAD}</p>
      </header>
      <ul className={styles.grid}>
        {STAFF_CARDS.map((card) => (
          <li key={card.slug}>
            <PersonCard card={card} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function monogram(card: StaffCard): string {
  return `${card.givenName.slice(0, 1)}${card.familyName.slice(0, 1)}`;
}

function PersonCard({ card }: { card: StaffCard }) {
  return (
    <article className={styles.card}>
      <span className={styles.mark} aria-hidden="true">
        {monogram(card)}
      </span>
      <p className={styles.role}>{card.role}</p>
      <h2 className={styles.name}>
        <span className={styles.given}>{card.givenName}</span> {card.familyName}
      </h2>
      <ul className={styles.contacts}>
        <li>
          <a href={staffPhoneHref(card)}>{formatStaffPhone(card)}</a>
        </li>
        <li>
          <a href={mailHref(card.email)}>{card.email}</a>
        </li>
      </ul>
      <Link className={styles.cta} to={`/komanda/${card.slug}`} data-brand-fill>
        Визитка
      </Link>
    </article>
  );
}
