/**
 * Apple Mail–style rich text compose: toolbar + contenteditable synced to #id_body.
 */
(function () {
  "use strict";

  const form = document.getElementById("hoocon-mail-compose-form");
  if (!form) {
    return;
  }

  const editor = form.querySelector(".hoocon-mail-compose__editor");
  const textarea = form.querySelector("#id_body");
  if (!editor || !textarea) {
    return;
  }

  const ALLOWED_TAGS = new Set([
    "P", "BR", "DIV", "SPAN", "UL", "OL", "LI", "B", "STRONG", "I", "EM", "U", "A", "BLOCKQUOTE",
  ]);
  const DROP_WITH_CONTENT = new Set([
    "SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "TEMPLATE", "NOSCRIPT", "SVG", "MATH",
  ]);

  function looksLikeHtml(text) {
    return /<(p|br|div|ul|ol|li|b|strong|i|em|u|a|span|blockquote)\b/i.test(text || "");
  }

  function safeHref(raw) {
    const value = (raw || "").trim();
    return /^(https?:|mailto:|tel:)/i.test(value) ? value : "";
  }

  function cleanNode(source, target) {
    source.childNodes.forEach(function (child) {
      if (child.nodeType === Node.TEXT_NODE) {
        target.appendChild(document.createTextNode(child.textContent));
        return;
      }
      if (child.nodeType !== Node.ELEMENT_NODE || DROP_WITH_CONTENT.has(child.tagName)) {
        return;
      }
      if (!ALLOWED_TAGS.has(child.tagName)) {
        cleanNode(child, target);
        return;
      }
      const copy = document.createElement(child.tagName.toLowerCase());
      if (child.tagName === "A") {
        const href = safeHref(child.getAttribute("href"));
        if (href) {
          copy.setAttribute("href", href);
          copy.setAttribute("rel", "noopener noreferrer");
        }
      }
      cleanNode(child, copy);
      target.appendChild(copy);
    });
  }

  function sanitizeHtml(html) {
    // DOMParser documents are inert: no scripts, no image loads, no handlers.
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const out = document.createElement("div");
    cleanNode(parsed.body, out);
    return out;
  }

  function plainToFragment(text) {
    const out = document.createElement("div");
    text.split(/\n{2,}/).forEach(function (block) {
      const p = document.createElement("p");
      block.split("\n").forEach(function (line, index) {
        if (index) {
          p.appendChild(document.createElement("br"));
        }
        p.appendChild(document.createTextNode(line));
      });
      out.appendChild(p);
    });
    return out;
  }

  function renderInitial(text) {
    const value = text || "";
    const clean = looksLikeHtml(value) ? sanitizeHtml(value) : plainToFragment(value);
    editor.replaceChildren.apply(editor, Array.from(clean.childNodes));
  }

  function syncToTextarea() {
    const html = editor.innerHTML.trim();
    textarea.value = html === "<br>" ? "" : html;
  }

  function refreshToolbarState() {
    form.querySelectorAll("[data-format]").forEach(function (button) {
      const command = button.getAttribute("data-format");
      let active = false;
      try {
        if (command === "bold") {
          active = document.queryCommandState("bold");
        } else if (command === "italic") {
          active = document.queryCommandState("italic");
        } else if (command === "underline") {
          active = document.queryCommandState("underline");
        }
      } catch (_err) {
        active = false;
      }
      button.classList.toggle("is-active", active);
    });
  }

  if (textarea.value) {
    renderInitial(textarea.value);
  }
  syncToTextarea();

  editor.addEventListener("paste", function (event) {
    const data = event.clipboardData;
    if (!data) {
      return;
    }
    event.preventDefault();
    const html = data.getData("text/html");
    const clean = html ? sanitizeHtml(html) : plainToFragment(data.getData("text/plain"));
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      return;
    }
    const range = selection.getRangeAt(0);
    range.deleteContents();
    const fragment = document.createDocumentFragment();
    Array.from(clean.childNodes).forEach(function (node) {
      fragment.appendChild(node);
    });
    const last = fragment.lastChild;
    range.insertNode(fragment);
    if (last) {
      range.setStartAfter(last);
      range.collapse(true);
      selection.removeAllRanges();
      selection.addRange(range);
    }
    syncToTextarea();
  });

  editor.addEventListener("input", function () {
    syncToTextarea();
    refreshToolbarState();
  });

  editor.addEventListener("keyup", refreshToolbarState);
  editor.addEventListener("mouseup", refreshToolbarState);

  form.addEventListener("submit", function () {
    syncToTextarea();
  });

  form.querySelectorAll("[data-format]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      const command = button.getAttribute("data-format");
      editor.focus();
      if (command === "createLink") {
        const url = safeHref(window.prompt("Адрес ссылки:", "https://"));
        if (url) {
          document.execCommand("createLink", false, url);
        }
      } else {
        document.execCommand(command, false, null);
      }
      syncToTextarea();
      refreshToolbarState();
    });
  });
})();
