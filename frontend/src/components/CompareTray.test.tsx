import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import { CompareProvider } from "../compare/CompareContext";
import { setSupportChatUnread } from "../utils/supportChatControl";
import { CompareTray } from "./CompareTray";

const renderDock = () =>
  renderToStaticMarkup(
    <MemoryRouter>
      <CompareProvider>
        <CompareTray showWhenEmpty />
      </CompareProvider>
    </MemoryRouter>,
  );

describe("CompareTray dock chat button", () => {
  it("mirrors the FAB unread badge while the dock replaces it on mobile", () => {
    setSupportChatUnread(3);
    const html = renderDock();
    expect(html).toContain("chatBadge");
    expect(html).toContain(">3</span>");
    expect(html).toContain("3 новых сообщений");
    setSupportChatUnread(0);
    expect(renderDock()).not.toContain("chatBadge");
  });

  it("caps the badge at 9+", () => {
    setSupportChatUnread(14);
    expect(renderDock()).toContain(">9+</span>");
    setSupportChatUnread(0);
  });

  it("keeps the badge pinned to the button corner", () => {
    const css = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "CompareTray.module.css"),
      "utf8",
    );
    expect(css).toContain(".chat {\n  position: relative");
    const badgeRule = css.split(".chatBadge {")[1].split("}")[0];
    expect(badgeRule).toContain("position: absolute");
    expect(badgeRule).toContain("border-radius: 999px");
    expect(badgeRule).toContain("var(--color-danger");
  });
});
