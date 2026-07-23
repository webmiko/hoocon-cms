import { describe, expect, it } from "vitest";

import { paraphraseSkuLead } from "./paraphraseSkuLead";

describe("paraphraseSkuLead", () => {
  it("rewrites fire-actuator lead without copying it verbatim", () => {
    const lead =
      "Электропривод 3 Нм для противопожарных клапанов с пружинным возвратом";
    const out = paraphraseSkuLead(lead);
    expect(out).not.toBe(lead);
    expect(out).toContain("противопожарных клапанов");
    expect(out).toContain("3 Нм");
    expect(out.startsWith("Применяется")).toBe(true);
  });

  it("falls back for free-form leads", () => {
    expect(paraphraseSkuLead("Крутящий момент 5 Нм, площадь < 0,5 м².")).toBe(
      "Назначение модели: крутящий момент 5 Нм, площадь < 0,5 м².",
    );
  });
});
