import { describe, expect, it } from "vitest";

import { AccountApiError } from "../account/api";
import { ApiError } from "../api/client";
import { leadFormErrors } from "../components/leadFormErrors";
import { drfErrorMessage, responseErrorMessage, userErrorMessage } from "./drfErrors";

describe("drfErrorMessage", () => {
  it("reads detail, non_field_errors, field lists and nested item errors", () => {
    expect(drfErrorMessage({ detail: "Слишком часто." })).toBe("Слишком часто.");
    expect(drfErrorMessage({ non_field_errors: ["Укажите артикул."] })).toBe("Укажите артикул.");
    expect(drfErrorMessage({ email: ["Введите правильный адрес."] })).toBe("Введите правильный адрес.");
    expect(drfErrorMessage({ items: [{}, { quantity: ["Не больше 100000."] }] })).toBe("Не больше 100000.");
    expect(drfErrorMessage(["Список."])).toBe("Список.");
    expect(drfErrorMessage({})).toBe("");
  });

  it("falls back by status when the body is empty (HTTP/2 has no statusText)", () => {
    expect(responseErrorMessage(400, {})).toBe("Проверьте введённые данные.");
    expect(responseErrorMessage(502, null)).toMatch(/Сервер временно недоступен/);
  });
});

describe("error classes carry readable text", () => {
  it("ApiError no longer says «API 400: Unknown error»", () => {
    const err = new ApiError(400, { items: [{ quantity: ["Не больше 100000."] }] });
    expect(err.message).toBe("Не больше 100000.");
    expect(new ApiError(500, {}).message).not.toMatch(/Unknown error|API 500/);
  });

  it("userErrorMessage hides «Failed to fetch» and foreign messages", () => {
    expect(userErrorMessage(new ApiError(429, { detail: "Подождите." }), "x")).toBe("Подождите.");
    expect(userErrorMessage(new AccountApiError(400, "Код неверный."), "x")).toBe("Код неверный.");
    expect(userErrorMessage(new TypeError("Failed to fetch"), "x")).toMatch(/Нет связи с сервером/);
    expect(userErrorMessage(new Error("boom"), "Не удалось отправить")).toBe("Не удалось отправить");
    expect(userErrorMessage({ a: 1 }, "Не удалось отправить")).toBe("Не удалось отправить");
  });
});

describe("leadFormErrors", () => {
  it("keeps inline fields and moves unshown ones to the error box", () => {
    const errors = leadFormErrors(400, {
      email: ["Введите правильный адрес."],
      phone: ["Неверный номер."],
      items: [{ quantity: ["Не больше 100000."] }],
      non_field_errors: ["Укажите sku или sku_code."],
    });
    expect(errors.email).toBe("Введите правильный адрес.");
    expect(errors.items).toBe("Не больше 100000.");
    expect(errors.detail).toContain("Неверный номер.");
    expect(errors.detail).toContain("Укажите sku или sku_code.");
    expect(Object.values(errors).join(" ")).not.toContain("[object Object]");
  });

  it("shows the server pdn_consent error under the consent checkbox", () => {
    const errors = leadFormErrors(400, { pdn_consent: ["Подтвердите согласие."] });
    expect(errors).toEqual({ pdn: "Подтвердите согласие." });
  });

  it("never returns an empty error set for a failed submit", () => {
    expect(leadFormErrors(429, {})).toEqual({ detail: "Слишком много попыток. Подождите минуту." });
  });
});
