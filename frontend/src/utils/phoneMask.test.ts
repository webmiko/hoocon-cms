import { describe, expect, it } from "vitest";

import {
  formatNational,
  formatPhone,
  guessPhoneCountryFromGeo,
  nationalFromInput,
  parsePhone,
} from "./phoneMask";

describe("formatNational", () => {
  it("masks Russia as (999) 999-99-99", () => {
    expect(formatNational("ru", "9991234567")).toBe("(999) 123-45-67");
    expect(formatNational("ru", "999")).toBe("(999)");
    expect(formatNational("ru", "99912")).toBe("(999) 12");
  });

  it("masks Belarus as (29) 999-99-99", () => {
    expect(formatNational("by", "291234567")).toBe("(29) 123-45-67");
  });
});

describe("formatPhone", () => {
  it("builds +7 (999) 999-99-99 example", () => {
    expect(formatPhone("ru", "9999999999")).toBe("+7 (999) 999-99-99");
  });

  it("keeps dial-only when national empty", () => {
    expect(formatPhone("ru", "")).toBe("+7");
    expect(formatPhone("by", "")).toBe("+375");
  });
});

describe("parsePhone", () => {
  it("detects RU / BY from full strings", () => {
    expect(parsePhone("+7 (999) 123-45-67")).toEqual({
      countryId: "ru",
      nationalDigits: "9991234567",
    });
    expect(parsePhone("+375 (29) 123-45-67")).toEqual({
      countryId: "by",
      nationalDigits: "291234567",
    });
  });

  it("defaults bare digits to Russia national", () => {
    expect(parsePhone("9991234567")).toEqual({
      countryId: "ru",
      nationalDigits: "9991234567",
    });
  });
});

describe("nationalFromInput", () => {
  it("strips formatting and caps length", () => {
    expect(nationalFromInput("ru", "(999) 123-45-67-extra")).toBe("9991234567");
    expect(nationalFromInput("by", "291234567890")).toBe("291234567");
  });
});

describe("guessPhoneCountryFromGeo", () => {
  it("maps EAEU timezones to phone countries", () => {
    expect(guessPhoneCountryFromGeo("Europe/Minsk", [])).toBe("by");
    expect(guessPhoneCountryFromGeo("Asia/Almaty", [])).toBe("kz");
    expect(guessPhoneCountryFromGeo("Asia/Yerevan", [])).toBe("am");
    expect(guessPhoneCountryFromGeo("Asia/Bishkek", [])).toBe("kg");
    expect(guessPhoneCountryFromGeo("Europe/Moscow", [])).toBe("ru");
  });

  it("falls back to language tags when timezone unknown", () => {
    expect(guessPhoneCountryFromGeo("UTC", ["ru-BY"])).toBe("by");
    expect(guessPhoneCountryFromGeo("UTC", ["kk-KZ", "ru"])).toBe("kz");
    expect(guessPhoneCountryFromGeo("UTC", ["en-US"])).toBe("ru");
  });
});
