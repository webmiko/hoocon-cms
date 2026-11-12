import { describe, expect, it } from "vitest";

import {
  formatRuPhone,
  formatStaffPhone,
  staffCardBySlug,
  staffPhoneHref,
  staffVCard,
  telegramHref,
  whatsappHref,
} from "./staffCards";

describe("staff card for Людмила Попова", () => {
  const card = staffCardBySlug("popova");

  it("is published at /komanda/popova", () => {
    expect(card).toBeDefined();
    expect(card?.role).toBe("Бренд-менеджер");
    expect(card?.email).toBe("assistant@hoocon.ru");
    expect(card?.wechatId).toBe("ludmilapopova");
  });

  it("formats the mobile the way the printed card shows it", () => {
    expect(formatRuPhone(card!.phone)).toBe("+7 (995) 780-70-18");
  });

  it("opens Telegram and WhatsApp on that same number", () => {
    expect(telegramHref(card!.telegram!)).toBe("https://t.me/+79957807018");
    expect(whatsappHref(card!.whatsapp!)).toBe("https://wa.me/79957807018");
  });

  it("puts the name, phone, mail and WeChat into the contact file", () => {
    const body = staffVCard(card!);
    expect(body.startsWith("BEGIN:VCARD\r\n")).toBe(true);
    expect(body).toContain("FN:Людмила Попова");
    expect(body).toContain("TEL;TYPE=CELL,VOICE:+79957807018");
    expect(body).toContain("EMAIL;TYPE=INTERNET:assistant@hoocon.ru");
    expect(body).toContain("WeChat: ludmilapopova");
    expect(body.endsWith("END:VCARD\r\n")).toBe(true);
  });
});

describe("UIS city line on office cards", () => {
  it("keeps Shevchenko on +7 (499) 995-12-77, extension 202", () => {
    const card = staffCardBySlug("shevchenko");
    expect(card?.role).toBe("Менеджер по продажам");
    expect(card?.email).toBe("alexander@hoocon.ru");
    expect(formatStaffPhone(card!)).toBe("+7 (499) 995-12-77 доб. 202");
    expect(staffPhoneHref(card!)).toBe("tel:+74999951277,202");
    expect(card?.telegram).toBeUndefined();
    const body = staffVCard(card!);
    expect(body).toContain("FN:Александр Шевченко");
    expect(body).toContain("TEL;TYPE=WORK,VOICE:+74999951277,202");
    expect(body).not.toContain("495");
  });

  it("keeps Shinkarenko on the same 499 number, extension 203", () => {
    const card = staffCardBySlug("shinkarenko");
    expect(card?.role).toBe("Менеджер отдела региональных продаж");
    expect(card?.email).toBe("larisa@hoocon.ru");
    expect(formatStaffPhone(card!)).toBe("+7 (499) 995-12-77 доб. 203");
    expect(staffPhoneHref(card!)).toBe("tel:+74999951277,203");
    const body = staffVCard(card!);
    expect(body).toContain("FN:Лариса Шинкаренко");
    expect(body).toContain("TEL;TYPE=WORK,VOICE:+74999951277,203");
    expect(body).not.toContain("495");
  });
});
