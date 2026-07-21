import { describe, expect, it } from "vitest";

import { mediaPurposeFromCategory } from "./mediaPurpose";

describe("mediaPurposeFromCategory", () => {
  it("maps air categories", () => {
    expect(
      mediaPurposeFromCategory("elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"),
    ).toBe("air");
    expect(
      mediaPurposeFromCategory(
        "elektronnye-otkazoustoychivye-vozdushnye-privody",
      ),
    ).toBe("air");
  });

  it("maps smoke categories", () => {
    expect(
      mediaPurposeFromCategory("elektroprivody-dlya-klapanov-dymoudaleniya"),
    ).toBe("smoke");
    expect(
      mediaPurposeFromCategory(
        "elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
      ),
    ).toBe("smoke");
  });

  it("maps fire categories", () => {
    expect(
      mediaPurposeFromCategory("elektroprivody-protivopozharnye-i-dymovye"),
    ).toBe("fire");
    expect(
      mediaPurposeFromCategory("elektroprivody-s-pruzhinnym-vozvratom"),
    ).toBe("fire");
  });

  it("maps ball valves and empty to valve", () => {
    expect(mediaPurposeFromCategory("sharovye-krany")).toBe("valve");
    expect(mediaPurposeFromCategory("")).toBe("valve");
    expect(mediaPurposeFromCategory(null)).toBe("valve");
  });

  it("keeps air when slug mentions bez-pruzhinnogo", () => {
    expect(
      mediaPurposeFromCategory(
        "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
      ),
    ).toBe("air");
  });
});
