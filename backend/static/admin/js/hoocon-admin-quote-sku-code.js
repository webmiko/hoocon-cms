/**
 * Quote line: the article code is read-only and follows the chosen SKU.
 * The server copies the code on save; this only shows it before save.
 */
(function () {
  "use strict";

  var LOOKUP = "/admin/crm/quote/sku-code/";

  function fill(select, input) {
    var id = select.value;
    if (!id) {
      input.value = "";
      return;
    }
    window
      .fetch(LOOKUP + "?id=" + encodeURIComponent(id), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
      .then(function (response) {
        if (!response.ok) {
          return null;
        }
        return response.json();
      })
      .then(function (data) {
        if (data && typeof data.sku_code === "string") {
          input.value = data.sku_code;
        }
      })
      .catch(function () {
        /* Save still copies the code from the selected SKU. */
      });
  }

  function bind(row) {
    if (!row || !row.querySelector) {
      return;
    }
    var select = row.querySelector("select[name$='-sku']");
    var input = row.querySelector("input[name$='-sku_code']");
    if (!select || !input || input.dataset.skuCodeBound === "1") {
      return;
    }
    input.dataset.skuCodeBound = "1";
    input.readOnly = true;
    var jq = window.django && window.django.jQuery;
    if (jq) {
      jq(select).on("change", function () {
        fill(select, input);
      });
    } else {
      select.addEventListener("change", function () {
        fill(select, input);
      });
    }
    if (select.value && !input.value) {
      fill(select, input);
    }
  }

  function scan(root) {
    var rows = (root || document).querySelectorAll("#items-data tr.form-row");
    Array.prototype.forEach.call(rows, bind);
  }

  function init() {
    if (!document.getElementById("items-data")) {
      return;
    }
    scan(document);
    var jq = window.django && window.django.jQuery;
    if (jq) {
      jq(document).on("formset:added", function (_event, row) {
        bind(row);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
