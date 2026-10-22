import { describe, expect, it } from "vitest";

import { EAC_DECLARATIONS, visibleEacDeclarations } from "./eacDeclarations";

describe("visibleEacDeclarations", () => {
  it("shows the declarations on the certificates view and hides them for manuals", () => {
    expect(visibleEacDeclarations({ q: "", series: "", kind: "" })).toHaveLength(3);
    expect(
      visibleEacDeclarations({ q: "", series: "", kind: "certificate" }).map((item) => item.id),
    ).toEqual(["eac-230v-2023", "eac-24v-2024", "eac-bv-2023"]);
    expect(visibleEacDeclarations({ q: "", series: "", kind: "manual" })).toEqual([]);
  });

  it("keeps drive declarations on DA, SA and HV, and the valve declaration on BR", () => {
    expect(visibleEacDeclarations({ q: "", series: "DA", kind: "certificate" })).toHaveLength(2);
    expect(visibleEacDeclarations({ q: "", series: "HV", kind: "" })).toHaveLength(2);
    expect(visibleEacDeclarations({ q: "", series: "H81", kind: "" })).toEqual([]);
    expect(
      visibleEacDeclarations({ q: "", series: "BR", kind: "certificate" }).map((item) => item.id),
    ).toEqual(["eac-bv-2023"]);
  });

  it("matches voltage words and does not offer a download url", () => {
    const only230 = visibleEacDeclarations({ q: "230", series: "", kind: "certificate" });
    expect(only230.map((item) => item.id)).toEqual(["eac-230v-2023"]);
    const only24 = visibleEacDeclarations({ q: "24", series: "SA", kind: "" });
    expect(only24.map((item) => item.id)).toEqual(["eac-24v-2024"]);
    const valves = visibleEacDeclarations({ q: "кран", series: "", kind: "certificate" });
    expect(valves.map((item) => item.id)).toEqual(["eac-bv-2023"]);
    for (const item of EAC_DECLARATIONS) {
      expect(item.src.endsWith(".webp")).toBe(true);
      expect("download" in item).toBe(false);
    }
  });
});
