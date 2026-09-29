import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const tsx = readFileSync(join(here, "SupportWidget.tsx"), "utf8");
const css = readFileSync(join(here, "SupportWidget.module.css"), "utf8");

describe("SupportWidget mobile chat", () => {
  it("uses the same 768px breakpoint for scroll lock and fullscreen CSS", () => {
    /*
     * Was 720px in JS vs 768px in CSS: at 721–768px the sheet was fullscreen
     * but the page behind it kept scrolling.
     */
    expect(tsx).toContain('matchMedia("(max-width: 768px)")');
    expect(css).toContain("@media (max-width: 768px)");
    expect(tsx).not.toContain("720px");
  });

  it("pins the open sheet to visualViewport so the keyboard keeps it visible", () => {
    /*
     * position:fixed tracks the layout viewport; the on-screen keyboard pans
     * the visual viewport on iOS/Android — header/composer must follow it.
     */
    expect(tsx).toContain("window.visualViewport");
    expect(tsx).toContain("vv.offsetTop");
    expect(tsx).toContain("vv.offsetLeft");
    expect(tsx).toContain("vv.height");
    expect(tsx).toContain('vv.addEventListener("resize"');
    expect(tsx).toContain('vv.addEventListener("scroll"');
  });

  it("mobile keyboard shows Send and unread reaches the shared store", () => {
    expect(tsx).toContain('enterKeyHint="send"');
    /* Dock «Чат» button needs the badge while the FAB is hidden. */
    expect(tsx).toContain("setSupportChatUnread");
  });

  it("keeps «Продолжить с ботом» visible on escalated chats", () => {
    /*
     * Escalated threads hid ALL branch buttons — including continue_bot,
     * the only way back to the bot. Now actions are filtered, not dropped.
     */
    expect(tsx).toContain('a.id === "continue_bot"');
    expect(tsx).toContain("messageActionsFor");
  });
});
