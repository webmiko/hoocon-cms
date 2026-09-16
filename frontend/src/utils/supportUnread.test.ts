import { describe, expect, it } from "vitest";

import {
  countSupportUnread,
  maxSupportMessageId,
} from "./supportUnread";

describe("supportUnread", () => {
  it("counts only outbound/system after last read id", () => {
    const messages = [
      { id: 1, direction: "inbound" },
      { id: 2, direction: "system" },
      { id: 3, direction: "outbound" },
      { id: 4, direction: "inbound" },
    ];
    expect(countSupportUnread(messages, 1)).toBe(2);
    expect(countSupportUnread(messages, 3)).toBe(0);
  });

  it("maxSupportMessageId keeps highest id", () => {
    expect(maxSupportMessageId([{ id: 2 }, { id: 7 }, { id: 5 }], 3)).toBe(7);
  });
});
