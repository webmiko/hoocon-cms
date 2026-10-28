/**
 * Admin: filter and bulk-toggle grouped permission checkboxes (groups / user permissions).
 */
(function () {
  "use strict";

  var bulkChangeBound = false;

  function normalize(text) {
    return (text || "").toLowerCase().trim();
  }

  function applyFilter(root, query) {
    var needle = normalize(query);
    root.querySelectorAll("[data-hoocon-perm-app]").forEach(function (appBlock) {
      var appVisible = false;
      appBlock.querySelectorAll("[data-hoocon-perm-model]").forEach(function (modelBlock) {
        var modelVisible = false;
        modelBlock.querySelectorAll("[data-hoocon-perm-item]").forEach(function (item) {
          var hay = normalize(item.textContent);
          var show = !needle || hay.indexOf(needle) !== -1;
          item.hidden = !show;
          if (show) {
            modelVisible = true;
          }
        });
        modelBlock.hidden = !modelVisible;
        if (modelVisible) {
          appVisible = true;
        }
      });
      appBlock.hidden = !appVisible;
    });
  }

  function permissionItemsInApp(appBlock, actionKey) {
    var items = appBlock.querySelectorAll("[data-hoocon-perm-item]");
    if (actionKey === "all") {
      return items;
    }
    return Array.prototype.filter.call(items, function (item) {
      return item.getAttribute("data-hoocon-perm-action") === actionKey;
    });
  }

  function checkboxesForItems(items) {
    var boxes = [];
    Array.prototype.forEach.call(items, function (item) {
      var input = item.querySelector('input[type="checkbox"][name]');
      if (input && !input.disabled) {
        boxes.push(input);
      }
    });
    return boxes;
  }

  function applyBulkToggle(appBlock, actionKey, checked) {
    var boxes = checkboxesForItems(permissionItemsInApp(appBlock, actionKey));
    boxes.forEach(function (box) {
      box.checked = checked;
      box.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  function syncBulkMasters(appBlock) {
    appBlock.querySelectorAll(".hoocon-perm-picker__bulk-toggle").forEach(function (toggle) {
      var actionKey = toggle.getAttribute("data-hoocon-perm-bulk-action") || "";
      var boxes = checkboxesForItems(permissionItemsInApp(appBlock, actionKey));
      if (!boxes.length) {
        toggle.checked = false;
        toggle.indeterminate = false;
        return;
      }
      var checkedCount = boxes.filter(function (box) {
        return box.checked;
      }).length;
      toggle.checked = checkedCount === boxes.length;
      toggle.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
    });
  }

  function bindBulkChangeDelegation() {
    if (bulkChangeBound) {
      return;
    }
    bulkChangeBound = true;
    document.addEventListener(
      "change",
      function (event) {
        var toggle = event.target;
        if (!toggle || !toggle.classList || !toggle.classList.contains("hoocon-perm-picker__bulk-toggle")) {
          return;
        }
        var appBlock = toggle.closest("[data-hoocon-perm-app]");
        if (!appBlock) {
          return;
        }
        var actionKey = toggle.getAttribute("data-hoocon-perm-bulk-action") || "";
        applyBulkToggle(appBlock, actionKey, toggle.checked);
        syncBulkMasters(appBlock);
      },
      true,
    );
    document.addEventListener(
      "change",
      function (event) {
        var box = event.target;
        if (!box || box.type !== "checkbox" || !box.name) {
          return;
        }
        var appBlock = box.closest("[data-hoocon-perm-app]");
        if (!appBlock) {
          return;
        }
        syncBulkMasters(appBlock);
      },
      true,
    );
  }

  function bindPicker(root) {
    var input = root.querySelector("[data-hoocon-perm-filter]");
    if (input && input.getAttribute("data-hoocon-perm-bound") !== "1") {
      input.setAttribute("data-hoocon-perm-bound", "1");
      input.addEventListener("input", function () {
        applyFilter(root, input.value);
      });
    }
    root.querySelectorAll("[data-hoocon-perm-app]").forEach(syncBulkMasters);
  }

  function init() {
    bindBulkChangeDelegation();
    document.querySelectorAll("[data-hoocon-perm-picker]").forEach(bindPicker);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
