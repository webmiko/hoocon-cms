import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const specs = vi.fn();
const deleteSpec = vi.fn();

vi.mock("./api", () => ({
  AccountApiError: class extends Error {
    detail = "";
  },
  accountApi: {
    specs: (...args: unknown[]) => specs(...args),
    deleteSpec: (...args: unknown[]) => deleteSpec(...args),
  },
}));

import SpecsPage from "./SpecsPage";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = (path: string) => readFileSync(join(srcDir, path), "utf8");

let root: Root | null = null;
let host: HTMLDivElement | null = null;

afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  root = null;
  host = null;
  specs.mockReset();
  deleteSpec.mockReset();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 5; i += 1) await Promise.resolve();
  });
}

describe("cabinet session scope", () => {
  it("probes /api/auth/me only on cabinet routes and the post-lead offer", () => {
    // The provider wrapped the whole app: /api/csrf + /api/auth/me on every public page.
    expect(src("main.tsx")).not.toContain("AccountAuthProvider");
    expect(src("account/CabinetGate.tsx")).toMatch(
      /<AccountAuthProvider>\{children\}<\/AccountAuthProvider>/,
    );
    expect(src("components/LeadForm.tsx")).toMatch(
      /<AccountAuthProvider>\s*<CabinetOffer email=\{leadEmail\} \/>\s*<\/AccountAuthProvider>/,
    );
  });

  it("cabinet pages refetch instead of reloading (a reload wiped the success notice)", () => {
    for (const page of ["account/SpecsPage.tsx", "account/RmaPage.tsx"]) {
      expect(src(page)).not.toContain("window.location.reload");
    }
  });

  it("SpecsPage refetches the list after delete", async () => {
    const spec = { id: 7, name: "Объект А", note: "", items: [], updated_at: "2026-10-09T10:00:00Z" };
    specs.mockResolvedValueOnce([spec]).mockResolvedValueOnce([]);
    deleteSpec.mockResolvedValue(undefined);
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    act(() => root?.render(<SpecsPage />));
    await flush();
    expect(host.textContent).toContain("Объект А");

    const remove = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === "Удалить");
    await act(async () => remove?.click());
    await flush();

    expect(deleteSpec).toHaveBeenCalledWith(7);
    expect(specs).toHaveBeenCalledTimes(2);
    expect(host.textContent).toContain("Спецификаций пока нет.");
  });
});
