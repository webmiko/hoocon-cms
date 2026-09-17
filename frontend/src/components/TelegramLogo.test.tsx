import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { TelegramLogo } from "./icons/TelegramLogo";

describe("TelegramLogo", () => {
  it("keeps horizontal wordmark inside the 131×42 viewBox", () => {
    const html = renderToStaticMarkup(<TelegramLogo withWordmark className="logo" />);
    const match = html.match(/translate\(([-\d.]+) ([-\d.]+)\) scale\(([\d.]+) ([\d.]+)\)/);
    expect(match).not.toBeNull();

    const tx = Number(match![1]);
    const ty = Number(match![2]);
    const scaleX = Number(match![3]);
    const scaleY = Number(match![4]);

    const minX = 40.4;
    const maxX = 120;
    const minY = 22;
    const maxY = 36;

    expect(tx + minX * scaleX).toBeGreaterThanOrEqual(45.5);
    expect(tx + maxX * scaleX).toBeLessThanOrEqual(131);
    expect(ty + minY * scaleY).toBeGreaterThanOrEqual(10.5);
    expect(ty + maxY * scaleY).toBeLessThanOrEqual(32.5);
    expect(scaleY).toBeGreaterThan(scaleX);
  });
});
