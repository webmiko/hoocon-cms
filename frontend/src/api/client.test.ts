import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";

function stubFetch() {
  const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function sentHeaders(fetchMock: ReturnType<typeof stubFetch>): Headers {
  const init = fetchMock.mock.calls[0][1] as RequestInit;
  return new Headers(init.headers);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch content type", () => {
  it("leaves multipart chat attachments to the browser (no JSON header)", async () => {
    const fetchMock = stubFetch();
    const file = new File(["png"], "photo.png", { type: "image/png" });
    await api.supportSendMessage("фото шильдика", undefined, undefined, file);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect(sentHeaders(fetchMock).has("Content-Type")).toBe(false);
    expect(sentHeaders(fetchMock).has("X-CSRFToken")).toBe(true);
  });

  it("marks JSON bodies as application/json", async () => {
    const fetchMock = stubFetch();
    await api.supportSendMessage("Вопрос по SA24");
    expect(sentHeaders(fetchMock).get("Content-Type")).toBe("application/json");
  });

  it("sends no content type on plain GET", async () => {
    const fetchMock = stubFetch();
    await api.categories();
    expect(sentHeaders(fetchMock).has("Content-Type")).toBe(false);
  });
});
