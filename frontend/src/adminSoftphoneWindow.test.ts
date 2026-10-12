import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Окно «Телефон» (backend/templates/admin/crm/softphone.html + hoocon-softphone-window.js).
// Реальный шаблон и реальный скрипт; подменены только внешние границы: библиотека UIS и HTTP.
const SOURCE = readFileSync(
  resolve(__dirname, "../../backend/static/admin/js/hoocon-softphone-window.js"),
  "utf8",
);
const TEMPLATE = readFileSync(
  resolve(__dirname, "../../backend/templates/admin/crm/softphone.html"),
  "utf8",
);

const SESSION_URL = "/admin/crm/softphone/session/";
const LOOKUP_URL = "/admin/crm/softphone/lookup/";
const CSRF = "csrf-token-for-test";

type StateHandler = (state: Record<string, unknown>) => void;

interface FakePhone {
  onState: StateHandler[];
  onError: ((code: string) => void)[];
  destroy: ReturnType<typeof vi.fn>;
  call: ReturnType<typeof vi.fn>;
  answer: ReturnType<typeof vi.fn>;
  terminate: ReturnType<typeof vi.fn>;
  sendDTMF: ReturnType<typeof vi.fn>;
  emit: (state: Record<string, unknown>) => void;
  fail: (code: string) => void;
}

function renderTemplate(): string {
  // Ветка «без блокировок» шаблона: Django-теги вычищаем, подставляем значения.
  const html = TEMPLATE.replace("{% if blockers %}1{% else %}0{% endif %}", "0")
    .replace(/\{% if blockers %\}[\s\S]*?\{% else %\}/, "")
    .replace(/\{% for key in "([^"]+)" %\}([\s\S]*?)\{% endfor %\}/, (_m, keys: string, body: string) =>
      [...keys].map((key) => body.replaceAll("{{ key }}", key)).join(""),
    )
    .replace(/\{%[^%]*%\}/g, "")
    .replace("{{ session_url }}", SESSION_URL)
    .replace("{{ lookup_url }}", LOOKUP_URL)
    .replace("{{ csrf_token }}", CSRF);
  const main = html.match(/<main[\s\S]*<\/main>/);
  if (!main) {
    throw new Error("в шаблоне окна телефона нет <main>");
  }
  return main[0];
}

const phones: FakePhone[] = [];
const createLib = vi.fn();

function newPhone(): FakePhone {
  const phone: FakePhone = {
    onState: [],
    onError: [],
    destroy: vi.fn(),
    call: vi.fn(),
    answer: vi.fn(),
    terminate: vi.fn(),
    sendDTMF: vi.fn(),
    emit: (state) => phone.onState.forEach((handler) => handler(state)),
    fail: (code) => phone.onError.forEach((handler) => handler(code)),
  };
  return phone;
}

const fetchMock = vi.fn();

async function flush(): Promise<void> {
  for (let i = 0; i < 4; i += 1) {
    await new Promise((resolveTick) => setTimeout(resolveTick, 0));
  }
}

function role(name: string): HTMLElement {
  const el = document.querySelector<HTMLElement>(`[data-role="${name}"]`);
  if (!el) {
    throw new Error(`нет data-role="${name}"`);
  }
  return el;
}

function click(selector: string): void {
  const el = document.querySelector<HTMLElement>(selector);
  if (!el) {
    throw new Error(`нет элемента ${selector}`);
  }
  el.click();
}

async function mountAndStart(): Promise<FakePhone> {
  document.body.innerHTML = renderTemplate();
  new Function(SOURCE)();
  click('[data-action="start"]');
  await flush();
  return phones[phones.length - 1];
}

let lookupAnswer: Record<string, unknown> = { found: false };

beforeEach(() => {
  phones.length = 0;
  createLib.mockReset();
  createLib.mockImplementation(() => {
    const phone = newPhone();
    phones.push(phone);
    return Object.assign(phone, {
      onStateChange: (handler: StateHandler) => phone.onState.push(handler),
      on: (event: string, handler: (code: string) => void) => {
        if (event === "error") {
          phone.onError.push(handler);
        }
      },
    });
  });
  (window as unknown as { uis_webrtc: unknown }).uis_webrtc = { create: createLib };
  lookupAnswer = { found: false };
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string) => {
    if (url === SESSION_URL) {
      return { ok: true, json: async () => ({ token: "tok-1", name: "Тест Телефона" }) };
    }
    return { ok: true, json: async () => lookupAnswer };
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("окно «Телефон»: запуск", () => {
  it("не трогает сеть и библиотеку, пока менеджер не нажал «Включить телефон»", () => {
    document.body.innerHTML = renderTemplate();
    new Function(SOURCE)();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(createLib).not.toHaveBeenCalled();
    expect(role("start").hidden).toBe(false);
  });

  it("берёт токен POST-ом с CSRF и запускает библиотеку именно с ним", async () => {
    await mountAndStart();
    expect(fetchMock).toHaveBeenCalledWith(
      SESSION_URL,
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        headers: expect.objectContaining({ "X-CSRFToken": CSRF }),
      }),
    );
    expect(createLib).toHaveBeenCalledWith(expect.objectContaining({ token: "tok-1" }));
    // Токен — только в памяти: ни в DOM, ни в хранилищах.
    expect(document.documentElement.outerHTML).not.toContain("tok-1");
    expect(JSON.stringify({ ...localStorage })).not.toContain("tok-1");
  });

  it("после ответа «на линии» показывает набор номера и прячет кнопку запуска", async () => {
    const phone = await mountAndStart();
    phone.emit({ available: true });
    expect(role("status").textContent).toBe("На линии");
    expect(role("start").hidden).toBe(true);
    expect(role("dialer").hidden).toBe(false);
  });
});

describe("окно «Телефон»: ошибки библиотеки (повтор без перезагрузки окна)", () => {
  it("ошибка микрофона: текст понятен, кнопка запуска возвращается, повтор создаёт новый телефон", async () => {
    const first = await mountAndStart();
    first.fail("microphoneAccessDenied");

    expect(role("error").hidden).toBe(false);
    expect(role("error").textContent).toContain("микрофон");
    expect(role("start").hidden).toBe(false); // без этого кнопка пропадала до перезагрузки окна
    expect(first.destroy).toHaveBeenCalledTimes(1);

    click('[data-action="start"]');
    await flush();
    expect(createLib).toHaveBeenCalledTimes(2);
    expect(phones).toHaveLength(2);
  });

  it("состояние с error (другой софтфон уже открыт) возвращает кнопку и просит закрыть UIS", async () => {
    const phone = await mountAndStart();
    phone.emit({ error: "appAlreadyOpened" });
    expect(role("error").textContent).toContain("Закройте софтфон UIS");
    expect(role("start").hidden).toBe(false);
    expect(role("dialer").hidden).toBe(true);
  });

  it("запоздалые события погашенного телефона не ломают новый запуск", async () => {
    const first = await mountAndStart();
    first.fail("telephonyIsUnavailable");
    click('[data-action="start"]');
    await flush();
    const second = phones[1];

    first.emit({ destroyed: true }); // библиотека досылает событие уничтоженного экземпляра
    first.fail("unknownError");
    expect(document.querySelector<HTMLElement>("#hsp")?.dataset.phase).toBe("connecting");

    second.emit({ available: true });
    expect(role("status").textContent).toBe("На линии");
    expect(role("error").hidden).toBe(true); // старая ошибка не висит поверх рабочего телефона
    expect(role("dialer").hidden).toBe(false);
  });

  it("неизвестный код ошибки показывает общий текст, а не undefined", async () => {
    const phone = await mountAndStart();
    phone.fail("somethingNew");
    expect(role("error").textContent).toContain("Ошибка телефона");
    expect(role("error").textContent).not.toContain("undefined");
  });
});

describe("окно «Телефон»: исходящий набор", () => {
  it("нормализует номер как CRM (8… → 7…) и звонит цифрами", async () => {
    const phone = await mountAndStart();
    phone.emit({ available: true });
    (document.querySelector('[data-role="number_input"]') as HTMLInputElement).value =
      "8 (916) 111-22-33";
    role("dial_form").dispatchEvent(new Event("submit", { cancelable: true }));
    expect(phone.call).toHaveBeenCalledTimes(1);
    expect(phone.call).toHaveBeenCalledWith("79161112233");
  });

  it("слишком короткий номер не уходит в телефонию", async () => {
    const phone = await mountAndStart();
    phone.emit({ available: true });
    (document.querySelector('[data-role="number_input"]') as HTMLInputElement).value = "12";
    role("dial_form").dispatchEvent(new Event("submit", { cancelable: true }));
    expect(phone.call).not.toHaveBeenCalled();
    expect(role("error").textContent).toContain("от 3 до 15");
  });
});

describe("окно «Телефон»: входящий звонок", () => {
  const incoming = {
    available: true,
    state: "progress",
    direction: "incoming",
    phoneNumber: "79161112233",
  };

  it("показывает имя клиента из CRM и ссылку на карточку, «Ответить» берёт трубку", async () => {
    lookupAnswer = {
      found: true,
      name: "Иван Тестов",
      company: "ООО Проверка",
      url: "/admin/crm/client/1/change/",
    };
    const phone = await mountAndStart();
    phone.emit(incoming);
    await flush();

    expect(fetchMock).toHaveBeenCalledWith(
      `${LOOKUP_URL}?phone=79161112233`,
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(role("direction").textContent).toBe("Входящий звонок");
    expect(role("who").textContent).toBe("Иван Тестов");
    expect(role("card").hidden).toBe(false);
    expect(role("card").getAttribute("href")).toBe("/admin/crm/client/1/change/");
    expect(role("answer").hidden).toBe(false);

    role("answer").click();
    expect(phone.answer).toHaveBeenCalledTimes(1);
  });

  it("незнакомый номер: показывает сам номер и не показывает ссылку на карточку", async () => {
    lookupAnswer = { found: false };
    const phone = await mountAndStart();
    phone.emit(incoming);
    await flush();
    expect(role("who").textContent).toBe("79161112233");
    expect(role("card").hidden).toBe(true);
  });

  it("«Отклонить» кладёт трубку, а после завершения карточка звонка исчезает", async () => {
    const phone = await mountAndStart();
    phone.emit(incoming);
    expect(role("hangup").textContent).toBe("Отклонить");
    role("hangup").click();
    expect(phone.terminate).toHaveBeenCalledTimes(1);

    phone.emit({ available: true, state: "terminated" });
    expect(role("call").hidden).toBe(true);
    expect(role("dialer").hidden).toBe(false);
  });

  it("в разговоре клавиатура шлёт DTMF, а вне разговора только набирает номер", async () => {
    const phone = await mountAndStart();
    phone.emit({ available: true });
    click('[data-key="5"]');
    expect(phone.sendDTMF).not.toHaveBeenCalled();
    expect((document.querySelector('[data-role="number_input"]') as HTMLInputElement).value).toBe(
      "5",
    );

    phone.emit({ ...incoming, state: "confirmed" });
    click('[data-key="7"]');
    expect(phone.sendDTMF).toHaveBeenCalledWith("7");
  });
});
