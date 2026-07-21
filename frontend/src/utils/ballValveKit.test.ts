import { describe, expect, it } from "vitest";

import {
  appendBallValveKitToMessage,
  defaultBallValveKitSelection,
  resolveBracketForDrive,
} from "./ballValveKit";

const kit = {
  drive_families: ["DA5FU24", "DA6MU24"],
  suffixes: ["-D", "-DS", "-A", "-AS"],
  bracket_by_drive: { DA5FU24: "BR-ML", DA6MU24: "BR-M" },
  bracket_hint: "BR-M / BR-ML (для DA…FU)",
};

describe("ballValveKit", () => {
  it("resolves BR-ML only for DA…FU", () => {
    expect(resolveBracketForDrive(kit, "DA5FU24")).toBe("BR-ML");
    expect(resolveBracketForDrive(kit, "DA6MU24")).toBe("BR-M");
  });

  it("appends drive and bracket lines to RFQ message", () => {
    const selection = {
      ...defaultBallValveKitSelection(kit),
      includeActuator: true,
      driveFamily: "DA5FU24",
      suffix: "-D",
      includeBracket: true,
      bracket: "BR-ML",
    };
    const message = appendBallValveKitToMessage(
      "Прошу подготовить КП на BV220A.",
      selection,
    );
    expect(message).toContain("Электропривод: DA5FU24-D");
    expect(message).toContain("Кронштейн: BR-ML");
  });

  it("omits kit lines when actuator not selected", () => {
    const selection = defaultBallValveKitSelection(kit);
    const message = appendBallValveKitToMessage("Прошу КП.", selection);
    expect(message).toBe("Прошу КП.");
  });
});
