/**
 * Public staff cards. Only fields listed here are shown — never the admin user.
 *
 * City line is the UIS virtual number +7 (499) 995-12-77
 * (wiki «Телефония Новосистем»): Alexander extension 202, Larisa 203.
 */

const CRLF = "\r\n";

/** UIS city number, E.164. Same line for every extension. */
const UIS_CITY_PHONE = "+74999951277";

export type StaffCard = {
  slug: string;
  givenName: string;
  familyName: string;
  role: string;
  /** E.164 with leading +, without the extension. */
  phone: string;
  /** Printed extension, e.g. "доб. 202". Omitted when the number is direct. */
  phoneExtension?: string;
  email: string;
  telegram?: string;
  whatsapp?: string;
  wechatId?: string;
  websiteLabel: string;
  websiteUrl: string;
};

export const STAFF_CARDS: readonly StaffCard[] = [
  {
    slug: "popova",
    givenName: "Людмила",
    familyName: "Попова",
    role: "Бренд-менеджер",
    phone: "+79957807018",
    email: "assistant@hoocon.ru",
    telegram: "+79957807018",
    whatsapp: "+79957807018",
    wechatId: "ludmilapopova",
    websiteLabel: "www.hoocon.ru",
    websiteUrl: "https://www.hoocon.ru",
  },
  {
    slug: "shevchenko",
    givenName: "Александр",
    familyName: "Шевченко",
    role: "Менеджер по продажам",
    phone: UIS_CITY_PHONE,
    phoneExtension: "доб. 202",
    email: "alexander@hoocon.ru",
    websiteLabel: "www.hoocon.ru",
    websiteUrl: "https://www.hoocon.ru",
  },
  {
    slug: "shinkarenko",
    givenName: "Лариса",
    familyName: "Шинкаренко",
    role: "Менеджер отдела региональных продаж",
    phone: UIS_CITY_PHONE,
    phoneExtension: "доб. 203",
    email: "larisa@hoocon.ru",
    websiteLabel: "www.hoocon.ru",
    websiteUrl: "https://www.hoocon.ru",
  },
];

export function staffCardBySlug(slug: string): StaffCard | undefined {
  const key = slug.trim().toLowerCase();
  return STAFF_CARDS.find((card) => card.slug === key);
}

export function staffFullName(card: StaffCard): string {
  return `${card.givenName} ${card.familyName}`;
}

/** +79957807018 → +7 (995) 780-70-18. Other numbers stay as stored. */
export function formatRuPhone(e164: string): string {
  const digits = e164.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("7")) {
    return `+7 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7, 9)}-${digits.slice(9, 11)}`;
  }
  return e164;
}

export function phoneHref(e164: string): string {
  return `tel:${e164}`;
}

/** Number as printed, including «доб. …» when the card has an extension. */
export function formatStaffPhone(card: StaffCard): string {
  const formatted = formatRuPhone(card.phone);
  return card.phoneExtension ? `${formatted} ${card.phoneExtension}` : formatted;
}

/**
 * Dial string. A comma is a pause, then the extension — how a phone dials
 * +7 (499) 995-12-77 and the UIS extension.
 */
export function staffPhoneHref(card: StaffCard): string {
  const extension = card.phoneExtension?.replace(/\D/g, "") ?? "";
  if (!extension) {
    return phoneHref(card.phone);
  }
  return `tel:${card.phone},${extension}`;
}

export function mailHref(email: string): string {
  return `mailto:${email}`;
}

/** t.me accepts a phone as +E.164 and opens the chat. */
export function telegramHref(e164: string): string {
  return `https://t.me/${e164}`;
}

export function whatsappHref(e164: string): string {
  return `https://wa.me/${e164.replace(/\D/g, "")}`;
}

function escapeVCard(value: string): string {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,");
}

/** Fold a content line at 75 octets. Continuation lines start with a space. */
function foldLine(line: string): string {
  const encoder = new TextEncoder();
  if (encoder.encode(line).length <= 75) {
    return line;
  }
  const parts: string[] = [];
  let current = "";
  let currentBytes = 0;
  for (const char of line) {
    const size = encoder.encode(char).length;
    const budget = parts.length === 0 ? 75 : 74;
    if (current && currentBytes + size > budget) {
      parts.push(current);
      current = char;
      currentBytes = size;
    } else {
      current += char;
      currentBytes += size;
    }
  }
  if (current) {
    parts.push(current);
  }
  return parts.map((part, index) => (index === 0 ? part : ` ${part}`)).join(CRLF);
}

function contactNote(card: StaffCard): string | undefined {
  const bits: string[] = [];
  if (card.telegram && card.whatsapp) {
    bits.push(`Telegram и WhatsApp: ${formatRuPhone(card.phone)}`);
  } else if (card.telegram) {
    bits.push(`Telegram: ${formatRuPhone(card.telegram)}`);
  } else if (card.whatsapp) {
    bits.push(`WhatsApp: ${formatRuPhone(card.whatsapp)}`);
  }
  if (card.wechatId) {
    bits.push(`WeChat: ${card.wechatId}`);
  }
  return bits.length ? bits.join(". ") : undefined;
}

function telLine(card: StaffCard): string {
  const extension = card.phoneExtension?.replace(/\D/g, "") ?? "";
  if (!extension) {
    return `TEL;TYPE=CELL,VOICE:${card.phone}`;
  }
  return `TEL;TYPE=WORK,VOICE:${card.phone},${extension}`;
}

/**
 * vCard 3.0 for “save contact” and for the QR a second phone scans.
 * Same payload in both places, so the file and the code stay identical.
 */
export function staffVCard(card: StaffCard): string {
  const note = contactNote(card);
  const lines = [
    "BEGIN:VCARD",
    "VERSION:3.0",
    "PRODID:-//Hoocon//Staff Card//RU",
    `N:${escapeVCard(card.familyName)};${escapeVCard(card.givenName)};;;`,
    `FN:${escapeVCard(staffFullName(card))}`,
    "ORG:HOOCON",
    `TITLE:${escapeVCard(card.role)}`,
    telLine(card),
    `EMAIL;TYPE=INTERNET:${card.email}`,
    `URL:${card.websiteUrl}`,
    ...(note ? [`NOTE:${escapeVCard(note)}`] : []),
    "END:VCARD",
  ];
  return `${lines.map(foldLine).join(CRLF)}${CRLF}`;
}

export function staffVCardFileName(card: StaffCard): string {
  return `${card.slug}.vcf`;
}
