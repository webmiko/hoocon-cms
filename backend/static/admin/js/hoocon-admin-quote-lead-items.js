/**
 * Empty «Позиции КП»: picking a lead fills its articles.
 * Quantity and code come from the lead. Price stays blank.
 * A typed row, or an auto row that already has a price, blocks a refill.
 * A failed lookup leaves the form as it is.
 */
(function () {
  "use strict";

  var LOOKUP = "/admin/crm/quote/lead-items/";
  var PREFIX = "items";

  function formset() {
    return document.getElementById(PREFIX + "-data");
  }

  function groups() {
    var root = formset();
    if (!root) {
      return [];
    }
    return Array.prototype.filter.call(root.querySelectorAll(":scope > tbody.form-group"), function (row) {
      return !row.classList.contains("empty-form");
    });
  }

  function field(row, suffix) {
    return row.querySelector("[name$='-" + suffix + "']");
  }

  function blank(row) {
    var sku = field(row, "sku");
    var price = field(row, "unit_price");
    var code = field(row, "sku_code");
    return (!sku || !sku.value) && (!price || !price.value.trim()) && (!code || !code.value.trim());
  }

  function manual(row) {
    return row.dataset.fromLead !== "1" && !blank(row);
  }

  function priced(row) {
    var price = field(row, "unit_price");
    return !!(price && price.value.trim());
  }

  function occupied(row) {
    return manual(row) || (row.dataset.fromLead === "1" && priced(row));
  }

  function clearFilled() {
    var guard = 0;
    while (guard < 40) {
      var marked = groups().filter(function (row) {
        var price = field(row, "unit_price");
        return row.dataset.fromLead === "1" && (!price || !price.value.trim());
      });
      if (!marked.length) {
        return;
      }
      var button = marked[marked.length - 1].querySelector(".delete-template");
      if (!button) {
        return;
      }
      button.click();
      guard += 1;
    }
  }

  function addRow() {
    var root = formset();
    if (!root) {
      return;
    }
    var button = root.querySelector(".add-row");
    if (button) {
      button.click();
    }
  }

  function setSku(select, item) {
    if (!item.sku_id) {
      return;
    }
    var jq = window.django && window.django.jQuery;
    var value = String(item.sku_id);
    if (!jq) {
      select.value = value;
      return;
    }
    var $select = jq(select);
    if (!$select.find("option").filter(function () { return this.value === value; }).length) {
      $select.append(new Option(item.label || item.sku_code, value, true, true));
    }
    $select.val(value).trigger("change");
  }

  function fill(row, item) {
    var sku = field(row, "sku");
    var code = field(row, "sku_code");
    var quantity = field(row, "quantity");
    var order = field(row, "sort_order");
    if (sku) {
      setSku(sku, item);
    }
    if (code) {
      code.value = item.sku_code || "";
    }
    if (quantity) {
      quantity.value = String(item.quantity || 1);
    }
    if (order) {
      order.value = String(item.sort_order || 0);
    }
    row.dataset.fromLead = "1";
  }

  function apply(items) {
    if (groups().some(occupied)) {
      return;
    }
    clearFilled();
    if (!items.length) {
      return;
    }
    var guard = 0;
    while (groups().filter(blank).length < items.length && guard < 40) {
      var before = groups().length;
      addRow();
      if (groups().length === before) {
        break;
      }
      guard += 1;
    }
    var blanks = groups().filter(blank);
    items.forEach(function (item, index) {
      if (blanks[index]) {
        fill(blanks[index], item);
      }
    });
  }

  function load(leadId, token) {
    if (!leadId) {
      apply([]);
      return;
    }
    window
      .fetch(LOOKUP + "?id=" + encodeURIComponent(leadId), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
      .then(function (response) {
        if (!response.ok || token.current !== leadId) {
          return null;
        }
        return response.json();
      })
      .then(function (data) {
        if (!data || token.current !== leadId) {
          return;
        }
        apply(data.items || []);
      })
      .catch(function () {
        /* Saving the lead link still works; lines stay as typed. */
      });
  }

  function init() {
    var lead = document.getElementById("id_lead");
    if (!lead || !formset()) {
      return;
    }
    var token = { current: "" };
    var request = function () {
      token.current = lead.value || "";
      load(token.current, token);
    };
    var jq = window.django && window.django.jQuery;
    if (jq) {
      jq(lead).on("change", request);
    } else {
      lead.addEventListener("change", request);
    }
    if (lead.value) {
      request();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
