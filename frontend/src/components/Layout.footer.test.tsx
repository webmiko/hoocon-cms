import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const layout = readFileSync(join(srcDir, "components/Layout.tsx"), "utf8");

describe("Layout footer cabinet link", () => {
  it("shows Личный кабинет in footer only when cabinet_enabled is on", () => {
    expect(layout).toContain("useCabinetEnabled");
    expect(layout.match(/<Link to="\/login">Личный кабинет<\/Link>/g)?.length).toBe(1);
    const mobileNav = layout.split('aria-label="Мобильное меню"')[1]?.split("</nav>")[0] ?? "";
    expect(mobileNav).not.toContain("Личный кабинет");
  });
});
