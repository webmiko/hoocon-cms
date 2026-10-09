import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

// Django Admin compose editor (loaded by admin/crm|leads compose templates).
const SOURCE = readFileSync(
  resolve(__dirname, "../../backend/static/admin/js/hoocon-mail-compose.js"),
  "utf8",
);

function mount(body: string): { editor: HTMLElement; textarea: HTMLTextAreaElement } {
  document.body.innerHTML = `
    <form id="hoocon-mail-compose-form">
      <div class="hoocon-mail-compose__editor" contenteditable="true"></div>
      <textarea id="id_body"></textarea>
    </form>`;
  const textarea = document.getElementById("id_body") as HTMLTextAreaElement;
  textarea.value = body;
  new Function(SOURCE)();
  const editor = document.querySelector(".hoocon-mail-compose__editor") as HTMLElement;
  return { editor, textarea };
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("hoocon-mail-compose initial body", () => {
  it("strips handlers and scripts from HTML bodies (stored XSS in Admin)", () => {
    const { editor, textarea } = mount(
      '<p>Здравствуйте, <img src=x onerror="alert(1)"><b onclick="x()">Иван</b></p><script>alert(2)</script>',
    );
    expect(editor.querySelector("img, script")).toBeNull();
    expect(editor.innerHTML).not.toMatch(/onerror|onclick|alert/);
    expect(editor.querySelector("b")?.textContent).toBe("Иван");
    expect(textarea.value).toBe(editor.innerHTML);
  });

  it("drops javascript: links but keeps safe ones", () => {
    const { editor } = mount(
      '<p><a href="javascript:alert(1)">bad</a> <a href="https://hoocon.ru/">ok</a></p>',
    );
    const links = editor.querySelectorAll("a");
    expect(links[0].hasAttribute("href")).toBe(false);
    expect(links[1].getAttribute("href")).toBe("https://hoocon.ru/");
  });

  it("renders plain text as escaped paragraphs", () => {
    const { editor } = mount("Строка <img src=x onerror=alert(1)>\nвторая\n\nабзац");
    expect(editor.querySelector("img")).toBeNull();
    expect(editor.querySelectorAll("p")).toHaveLength(2);
    expect(editor.querySelector("p")?.textContent).toContain("<img src=x");
  });
});
