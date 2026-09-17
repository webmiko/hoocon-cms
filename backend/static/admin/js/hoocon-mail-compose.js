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

  function looksLikeHtml(text) {
    const value = (text || "").trim().toLowerCase();
    if (!value.startsWith("<")) {
      return false;
    }
    return /<(p|br|div|ul|ol|li|b|strong|i|em|a)\b/.test(value);
  }

  function plainToHtml(text) {
    if (!text) {
      return "";
    }
    if (looksLikeHtml(text)) {
      return text;
    }
    return text
      .split(/\n{2,}/)
      .map(function (block) {
        const escaped = block
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;");
        return "<p>" + escaped.replace(/\n/g, "<br>") + "</p>";
      })
      .join("");
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

  editor.innerHTML = plainToHtml(textarea.value);
  syncToTextarea();

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
        const url = window.prompt("Адрес ссылки:", "https://");
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
