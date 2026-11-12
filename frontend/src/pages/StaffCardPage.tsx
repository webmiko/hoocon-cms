import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { encode } from "uqr";

import "@fontsource/montserrat/cyrillic-400.css";
import "@fontsource/montserrat/latin-400.css";

import { Seo } from "../components/Seo";
import {
  formatRuPhone,
  formatStaffPhone,
  mailHref,
  staffCardBySlug,
  staffFullName,
  staffPhoneHref,
  staffVCard,
  staffVCardFileName,
  telegramHref,
  whatsappHref,
  type StaffCard,
} from "../content/staffCards";
import styles from "./StaffCardPage.module.css";

/**
 * One public staff card, without the catalog header.
 * The route sits outside Layout so the page matches the printed card.
 */
export function StaffCardPage() {
  const { slug = "" } = useParams();
  const card = staffCardBySlug(slug);
  useLightCanvas();

  if (!card) {
    return (
      <main className={styles.page}>
        <Seo title="Визитка не найдена" noindex />
        <div className={styles.card}>
          <Logo />
          <h1 className={styles.name}>Такой визитки нет</h1>
          <p className={styles.missing}>
            <a href="https://www.hoocon.ru">www.hoocon.ru</a>
          </p>
        </div>
      </main>
    );
  }

  return <Card card={card} />;
}

function Card({ card }: { card: StaffCard }) {
  const [wechatCopied, setWechatCopied] = useState(false);
  const name = staffFullName(card);
  const phone = formatStaffPhone(card);
  const vcard = useMemo(() => staffVCard(card), [card]);
  const messengers = Boolean(card.telegram || card.whatsapp || card.wechatId);

  useEffect(() => {
    if (!wechatCopied) {
      return undefined;
    }
    const timer = window.setTimeout(() => setWechatCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [wechatCopied]);

  async function copyWeChat() {
    const id = card.wechatId;
    if (!id) {
      return;
    }
    try {
      await navigator.clipboard.writeText(id);
    } catch {
      const area = document.createElement("textarea");
      area.value = id;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    setWechatCopied(true);
  }

  function saveContact() {
    const blob = new Blob([vcard], { type: "text/vcard;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = staffVCardFileName(card);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <main className={styles.page}>
      <Seo
        title={`${name}, ${card.role}`}
        description={
          messengers
            ? `${card.role} Hoocon. Телефон, почта и мессенджеры на визитке.`
            : `${card.role} Hoocon. Телефон и почта на визитке.`
        }
        path={`/komanda/${card.slug}`}
        noindex
      />
      <article className={`${styles.card} ${styles.person}`}>
        <div className={styles.identity}>
          <h1 className={styles.name}>
            <span className={styles.given}>{card.givenName}</span> {card.familyName}
          </h1>
          <p className={styles.role}>{card.role}</p>
          <hr className={styles.rule} />
          <ul className={styles.list}>
            <li>
              <a className={styles.row} href={staffPhoneHref(card)}>
                <PhoneIcon />
                <span className={styles.label}>{phone}</span>
              </a>
            </li>
            <li>
              <a className={styles.row} href={mailHref(card.email)}>
                <MailIcon />
                <span className={styles.label}>{card.email}</span>
              </a>
            </li>
            {card.telegram ? (
              <li>
                <a
                  className={styles.row}
                  href={telegramHref(card.telegram)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <PlaneIcon />
                  <span className={styles.label}>Telegram · {formatRuPhone(card.telegram)}</span>
                </a>
              </li>
            ) : null}
            {card.whatsapp ? (
              <li>
                <a
                  className={styles.row}
                  href={whatsappHref(card.whatsapp)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ChatIcon />
                  <span className={styles.label}>WhatsApp · {formatRuPhone(card.whatsapp)}</span>
                </a>
              </li>
            ) : null}
            {card.wechatId ? (
              <li>
                <button type="button" className={styles.row} onClick={() => void copyWeChat()}>
                  <BubblesIcon />
                  <span className={styles.label}>
                    {wechatCopied ? "WeChat · скопировано" : `WeChat · ${card.wechatId}`}
                  </span>
                </button>
              </li>
            ) : null}
            <li>
              <a className={styles.row} href={card.websiteUrl}>
                <GlobeIcon />
                <span className={styles.label}>{card.websiteLabel}</span>
              </a>
            </li>
          </ul>
        </div>
        <div className={styles.side}>
          <Logo />
          <ContactQr value={vcard} />
          <p className={styles.caption}>Наведите камеру, чтобы сохранить контакт</p>
          <button type="button" className={styles.save} onClick={saveContact}>
            Сохранить контакт
          </button>
        </div>
        <p className="sr-only" aria-live="polite">
          {wechatCopied ? "ID WeChat скопирован" : ""}
        </p>
      </article>
    </main>
  );
}

function Logo() {
  return (
    <img
      className={styles.logo}
      src="/logo.svg"
      alt="Hoocon"
      width={248}
      height={63}
      decoding="async"
    />
  );
}

/** White page behind the card, including the overscroll past the footer colour. */
function useLightCanvas() {
  useEffect(() => {
    const root = document.documentElement;
    const previous = root.style.backgroundColor;
    root.style.backgroundColor = "#ffffff";
    return () => {
      root.style.backgroundColor = previous;
    };
  }, []);
}

function ContactQr({ value }: { value: string }) {
  const qr = useMemo(() => encode(value, { ecc: "M", border: 4 }), [value]);
  const cells: ReactNode[] = [];
  for (let y = 0; y < qr.size; y += 1) {
    const row = qr.data[y] ?? [];
    for (let x = 0; x < qr.size; x += 1) {
      if (row[x]) {
        cells.push(<rect key={`${x}:${y}`} x={x} y={y} width="1" height="1" />);
      }
    }
  }
  return (
    <svg
      className={styles.qr}
      viewBox={`0 0 ${qr.size} ${qr.size}`}
      role="img"
      aria-label="QR-код с контактом"
      shapeRendering="crispEdges"
    >
      <rect width={qr.size} height={qr.size} fill="#ffffff" />
      <g fill="#111111">{cells}</g>
    </svg>
  );
}

function iconProps() {
  return {
    className: styles.icon,
    viewBox: "0 0 24 24",
    "aria-hidden": true as const,
    focusable: false as const,
  };
}

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function PhoneIcon() {
  return (
    <svg {...iconProps()}>
      <path
        {...stroke}
        d="M8 3.8h2.1c.4 0 .8.3.9.7l.7 2.2a1 1 0 0 1-.3 1L9.8 9a12.2 12.2 0 0 0 5.2 5.2l1.3-1.6a1 1 0 0 1 1-.3l2.2.7c.4.1.7.5.7.9V16a2.2 2.2 0 0 1-2.2 2.2A13.2 13.2 0 0 1 5.8 6a2.2 2.2 0 0 1 2.2-2.2z"
      />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg {...iconProps()}>
      <rect {...stroke} x="3.5" y="5.5" width="17" height="13" rx="1.6" />
      <path {...stroke} d="M4.2 7.2 12 12.4l7.8-5.2" />
    </svg>
  );
}

function PlaneIcon() {
  return (
    <svg {...iconProps()}>
      <path {...stroke} d="M20.5 4.5 3.8 11.2l5.4 1.9M9.2 13.1 11 19.2l2.2-3.4 4.2 3.1L20.5 4.5z" />
      <path {...stroke} d="M9.2 13.1 18.2 7" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg {...iconProps()}>
      <path {...stroke} d="M12 4.4a7.1 7.1 0 0 0-6.1 10.7L4.6 19.4l4.4-1.2A7.1 7.1 0 1 0 12 4.4z" />
      <path {...stroke} d="M9.4 10.3c.3 1.8 1.7 3.1 3.4 3.4" />
    </svg>
  );
}

function BubblesIcon() {
  return (
    <svg {...iconProps()}>
      <rect {...stroke} x="3.2" y="5" width="10.2" height="7.4" rx="2" />
      <path {...stroke} d="M6.2 12.4 5 15.2l3.1-1.6" />
      <rect {...stroke} x="10.2" y="10.2" width="10.4" height="7.2" rx="2" fill="#ffffff" />
      <path {...stroke} d="M13.4 17.4 12.4 20l2.8-1.6" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg {...iconProps()}>
      <circle {...stroke} cx="12" cy="12" r="8" />
      <path {...stroke} d="M4 12h16" />
      <path
        {...stroke}
        d="M12 4c2.1 2.2 3.2 4.9 3.2 8s-1.1 5.8-3.2 8c-2.1-2.2-3.2-4.9-3.2-8s1.1-5.8 3.2-8z"
      />
    </svg>
  );
}
