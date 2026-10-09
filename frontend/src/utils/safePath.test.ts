import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { safeSameOriginPath } from "./safePath";

const ORIGIN = "https://hoocon.ru";

/* Browsers read these as //evil.com — a push click must never open them. */
const OFFSITE = ["/\\evil.com", "/\\/evil.com", "/\t/evil.com", "//evil.com", "https://evil.com/", "evil.com"];

/** Admin PWA service worker (served at /admin/sw.js), evaluated with a fake ``self``. */
function adminSafePath(): (raw: unknown) => string {
  const source = readFileSync(resolve(__dirname, "../../../backend/static/admin/js/hoocon-admin-sw.js"), "utf8");
  const fakeSelf = { addEventListener: () => undefined, location: { origin: ORIGIN } };
  return new Function("self", `${source}\nreturn safeAdminPath;`)(fakeSelf);
}

describe("safeSameOriginPath (public sw.ts)", () => {
  it.each(OFFSITE)("rejects %j", (raw) => {
    expect(safeSameOriginPath(raw, ORIGIN)).toBe("/");
  });

  it("keeps same-origin path, query and hash", () => {
    expect(safeSameOriginPath("/account/leads?x=1#top", ORIGIN)).toBe("/account/leads?x=1#top");
    expect(safeSameOriginPath(undefined, ORIGIN)).toBe("/");
  });
});

describe("safeAdminPath (admin sw.js)", () => {
  const safeAdminPath = adminSafePath();

  it.each(OFFSITE)("rejects %j", (raw) => {
    expect(safeAdminPath(raw)).toBe("/admin/");
  });

  it("keeps Admin paths", () => {
    expect(safeAdminPath("/admin/leads/lead/5/change/?a=1")).toBe("/admin/leads/lead/5/change/?a=1");
  });
});
