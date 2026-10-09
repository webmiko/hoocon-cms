import { afterEach, describe, expect, it, vi } from "vitest";

import { accountApi } from "./api";

function clearCookies(): void {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
}

afterEach(() => {
  vi.unstubAllGlobals();
  clearCookies();
});

describe("accountApi CSRF", () => {
  it("fetches the csrftoken cookie before the first POST (auth endpoints enforce CSRF)", async () => {
    clearCookies();
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/csrf/") {
        document.cookie = "csrftoken=tok123; path=/";
        return new Response(JSON.stringify({ csrfToken: "tok123" }), { status: 200 });
      }
      return new Response(JSON.stringify({ email: "a@b.test" }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await accountApi.login("a@b.test", "pw");

    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(["/api/csrf/", "/api/auth/login/"]);
    const headers = (fetchMock.mock.calls[1] as unknown as [string, RequestInit])[1]
      .headers as Record<string, string>;
    expect(headers["X-CSRFToken"]).toBe("tok123");
  });

  it("does not refetch the token when the cookie is already set", async () => {
    document.cookie = "csrftoken=ready; path=/";
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await accountApi.login("a@b.test", "pw");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("accountApi 152-ФЗ consent", () => {
  it("sends pdn_consent with code-login start and registration (server rejects without it)", async () => {
    document.cookie = "csrftoken=ready; path=/";
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ challenge_id: "c1" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await accountApi.otpStart("a@b.test", 1, true);
    await accountApi.register({
      email: "a@b.test",
      password: "pw-long-enough",
      form_start_ts: 1,
      pdn_consent: true,
    });

    const bodies = fetchMock.mock.calls.map((c) =>
      JSON.parse(String((c as unknown as [string, RequestInit])[1].body)),
    );
    expect(bodies[0]).toMatchObject({ email: "a@b.test", pdn_consent: true });
    expect(bodies[1]).toMatchObject({ email: "a@b.test", pdn_consent: true });
  });
});
