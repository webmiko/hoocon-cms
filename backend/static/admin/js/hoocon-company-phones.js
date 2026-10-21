/**
 * Company card: one phone input by default, «Добавить телефон» for the next.
 * Each row dials only its own number (a tel: link), not the whole list.
 */
(function () {
  "use strict";

  function digitsFor(raw) {
    var digits = String(raw || "").replace(/\D+/g, "");
    if (digits.length === 11 && digits.charAt(0) === "8") {
      digits = "7" + digits.slice(1);
    } else if (digits.length === 10) {
      digits = "7" + digits;
    }
    return digits;
  }

  function refresh(row) {
    var input = row.querySelector("input[name='phone']");
    var link = row.querySelector("a");
    if (!input || !link) {
      return;
    }
    var digits = digitsFor(input.value);
    if (digits.length >= 10 && digits.length <= 15) {
      link.href = "tel:+" + digits;
      link.hidden = false;
    } else {
      link.hidden = true;
      link.removeAttribute("href");
    }
  }

  function bind(row) {
    var input = row.querySelector("input[name='phone']");
    if (!input || input.dataset.phoneBound) {
      return;
    }
    input.dataset.phoneBound = "1";
    input.addEventListener("input", function () {
      refresh(row);
    });
  }

  function init(root) {
    if (root.dataset.phonesReady) {
      return;
    }
    root.dataset.phonesReady = "1";
    root.querySelectorAll(".hoocon-phones__row").forEach(bind);
    var add = root.querySelector("[data-add-phone]");
    if (!add) {
      return;
    }
    add.addEventListener("click", function () {
      var rows = root.querySelectorAll(".hoocon-phones__row");
      var last = rows[rows.length - 1];
      if (!last) {
        return;
      }
      var copy = last.cloneNode(true);
      var input = copy.querySelector("input");
      input.value = "";
      input.removeAttribute("id");
      delete input.dataset.phoneBound;
      last.after(copy);
      bind(copy);
      refresh(copy);
      input.focus();
    });
  }

  function boot() {
    document.querySelectorAll(".hoocon-phones").forEach(init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
