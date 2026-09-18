import { describe, expect, it, vi } from "vitest";

import { loadSupportChannelsWithRetry } from "./useSupportChannels";

describe("loadSupportChannelsWithRetry", () => {
  it("retries after backend boot race and returns bot channels", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error("backend down"))
      .mockResolvedValueOnce([
        {
          channel: "telegram_bot",
          label: "Telegram",
          deep_link: "https://t.me/HooconMsk_bot?start=support",
          provider: "telegram",
          kind: "bot",
        },
      ]);
    const sleep = vi.fn(async () => undefined);

    const channels = await loadSupportChannelsWithRetry(fetcher, {
      maxAttempts: 2,
      retryBaseMs: 10,
      sleep,
    });

    expect(channels).toHaveLength(1);
    expect(channels[0]?.channel).toBe("telegram_bot");
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledWith(10);
  });
});
