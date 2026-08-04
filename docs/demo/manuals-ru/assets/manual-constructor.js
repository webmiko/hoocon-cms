/**
 * Manual constructor — edit text/tables, insert images into A4×2 slots.
 * Works on template-kit / constructor page; crop panel via photo-crop-tool.js.
 */
(function () {
  "use strict";

  var DRAFT_KEY = "hoocon-manual-constructor:draft:v1";
  var TEMPLATES = [
    { id: "kit", label: "Бланк (полный каркас)", url: "template-kit.html" },
    { id: "v24", label: "Шаблон V24 (24 В)", url: "template-v24.html" },
    { id: "v230", label: "Шаблон V230 (230 В)", url: "template-v230.html" },
    { id: "uq", label: "Эталон UQ (заполненный)", url: "template-uq.html" },
  ];

  var EDIT_SELECTORS = [
    ".banner",
    ".prose",
    ".aux-note",
    ".torque",
    ".doc-title-line",
    ".doc-title",
    ".lead-heading",
    ".lead-intro",
    ".lead-list li",
    ".sku-list li",
    ".running-head",
    ".running-foot",
    ".unlock-hint",
    ".rotation-copy p",
    ".rotation-label",
    ".data-table td",
    ".toolbar > strong",
  ];

  var fileInput = null;
  var activeSlot = null;
  var saveTimer = null;

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function $all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function isConstructorPage() {
    if (document.body.hasAttribute("data-constructor")) return true;
    if (document.body.hasAttribute("data-constructor-kit")) return true;
    if (/constructor\.html$/i.test(location.pathname)) return true;
    if (/template-kit\.html$/i.test(location.pathname)) return true;
    if (location.hash === "#ctor" || /[?&]ctor=1\b/.test(location.search)) return true;
    return false;
  }

  function ensureFileInput() {
    if (fileInput) return fileInput;
    fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "image/png,image/jpeg,image/webp,image/svg+xml";
    fileInput.hidden = true;
    document.body.appendChild(fileInput);
    fileInput.addEventListener("change", function () {
      var file = fileInput.files && fileInput.files[0];
      fileInput.value = "";
      if (!file || !activeSlot) return;
      var reader = new FileReader();
      reader.onload = function () {
        placeImage(activeSlot, String(reader.result || ""), file.name);
        activeSlot = null;
        scheduleSave();
      };
      reader.readAsDataURL(file);
    });
    return fileInput;
  }

  function findImgInSlot(slot) {
    return slot.querySelector("img[data-slot], img.product-photo, img.lead-photo, img.aux-diagram, img");
  }

  function syncSlotEmpty(slot) {
    var img = findImgInSlot(slot);
    var empty = !img || !img.getAttribute("src") || img.hasAttribute("data-empty");
    slot.classList.toggle("is-empty", empty);
    if (img) {
      if (empty) {
        img.hidden = true;
        img.setAttribute("data-empty", "1");
      } else {
        img.hidden = false;
        img.removeAttribute("data-empty");
      }
    }
    var label = slot.querySelector(".img-slot-label");
    if (label) label.hidden = !empty;
  }

  function placeImage(slot, dataUrl, filename) {
    var img = findImgInSlot(slot);
    if (!img) {
      img = document.createElement("img");
      img.alt = "";
      slot.appendChild(img);
    }
    var slotName = img.getAttribute("data-slot") || slot.getAttribute("data-slot") || "image";
    img.setAttribute("data-slot", slotName);
    if (slotName === "product" && !img.classList.contains("product-photo")) {
      img.classList.add("product-photo");
    }
    if (slotName === "lead" && !img.classList.contains("lead-photo")) {
      img.classList.add("lead-photo");
    }
    if (slotName === "aux-diagram" && !img.classList.contains("aux-diagram")) {
      img.classList.add("aux-diagram");
    }
    img.src = dataUrl;
    img.removeAttribute("data-empty");
    img.hidden = false;
    if (filename) img.setAttribute("data-filename", filename);
    /* Clear live crop so new bitmap shows full frame. */
    img.style.clipPath = "";
    img.style.webkitClipPath = "";
    img.style.transform = "";
    syncSlotEmpty(slot);
    if (typeof window.hooconPhotoCropRefresh === "function") {
      window.hooconPhotoCropRefresh();
    }
    if (typeof window.fitSheet1Type === "function") {
      window.requestAnimationFrame(window.fitSheet1Type);
    }
  }

  function ensureKitSlotsFromPlaceholders() {
    /* V24/V230 use photo-fallback / «См. PDF» — turn into real image slots. */
    $all(".product-col .media, .summary-media").forEach(function (slot) {
      if (slot.querySelector("img")) return;
      var fb = slot.querySelector(".photo-fallback");
      if (fb) fb.remove();
      var isLead = slot.classList.contains("summary-media");
      var img = document.createElement("img");
      img.className = isLead ? "lead-photo" : "product-photo";
      img.setAttribute("data-slot", isLead ? "lead" : "product");
      img.setAttribute("data-empty", "1");
      img.hidden = true;
      img.alt = "";
      slot.appendChild(img);
      slot.classList.add("img-slot");
      if (isLead) slot.classList.add("summary-media");
      else {
        slot.classList.add("product-media");
        if (!slot.style.getPropertyValue("--media-h")) {
          slot.style.setProperty("--media-h", "72mm");
        }
      }
    });

    var diagrams = $(".diagrams");
    if (diagrams && !diagrams.querySelector("img, .img-slot, figure.diagram")) {
      diagrams.innerHTML =
        '<figure class="diagram diagram-wide wiring-figure">' +
        '<div class="wiring-board img-slot">' +
        '<img src="" alt="Схема подключения" data-slot="wiring" data-empty="1" hidden>' +
        '<span class="img-slot-label">Схема подключения</span></div></figure>' +
        '<figure class="diagram diagram-wide img-slot">' +
        '<h2 class="banner">Габаритные размеры привода (мм)</h2>' +
        '<img src="" alt="" data-slot="dimensions" data-empty="1" hidden>' +
        '<span class="img-slot-label">Габариты</span></figure>' +
        '<figure class="diagram diagram-wide diagram-rotation">' +
        '<h2 class="banner">Изменение направления вращения</h2>' +
        '<div class="rotation-panel img-slot">' +
        '<div class="rotation-copy"><p contenteditable="true" class="ctor-editable">' +
        "Текст про направление вращения — подставьте из PDF.</p></div>" +
        '<img src="" alt="" data-slot="rotation" data-empty="1" hidden>' +
        '<span class="img-slot-label">Направление вращения</span></div></figure>';
    }
  }

  function markImgSlots() {
    ensureKitSlotsFromPlaceholders();
    var hosts = $all(
      ".product-media, .summary-media, .aux-diagram-media, .unlock-media, " +
        ".wiring-board, .rotation-panel, .diagram.img-slot, .media.img-slot",
    );
    hosts.forEach(function (slot) {
      slot.classList.add("img-slot");
      if (!slot.querySelector(".img-slot-label")) {
        var lab = document.createElement("span");
        lab.className = "img-slot-label";
        lab.textContent = slotLabel(slot);
        slot.appendChild(lab);
      }
      syncSlotEmpty(slot);
      if (slot.dataset.ctorSlotBound) return;
      slot.dataset.ctorSlotBound = "1";
      slot.addEventListener("click", function (ev) {
        if (!document.body.classList.contains("ctor-edit")) return;
        if (ev.target.closest("a, button, input, .photo-crop-panel")) return;
        /* Allow text clicks inside rotation-copy */
        if (ev.target.closest(".rotation-copy, .unlock-hint, .wiring-ru-headers, .photo-rows")) {
          if (!ev.target.classList.contains("img-slot-label") && ev.target !== slot) return;
        }
        activeSlot = slot;
        ensureFileInput().click();
      });
    });
  }

  function slotLabel(slot) {
    if (slot.classList.contains("product-media")) return "Фото продукта";
    if (slot.classList.contains("summary-media")) return "Фото обзора (lead)";
    if (slot.classList.contains("aux-diagram-media")) return "Схема aux";
    if (slot.classList.contains("unlock-media")) return "Разблокировка";
    if (slot.classList.contains("wiring-board")) return "Схема подключения";
    if (slot.classList.contains("rotation-panel")) return "Направление вращения";
    if (slot.querySelector(".banner") && /Габарит/i.test(slot.textContent || "")) {
      return "Габариты";
    }
    return "Вставить изображение";
  }

  function enableTextEditing() {
    document.body.classList.add("ctor-edit");
    EDIT_SELECTORS.forEach(function (sel) {
      $all(sel).forEach(function (el) {
        if (el.closest(".photo-crop-panel, #ctor-bar, #ctor-table-tools")) return;
        if (el.closest(".logo, .col-guide, .photo-rows, .wiring-ru-headers")) return;
        el.contentEditable = "true";
        el.classList.add("ctor-editable");
        el.spellcheck = true;
      });
    });
    document.addEventListener("input", onEditInput, true);
    document.addEventListener("focusin", onFocusIn, true);
  }

  function onEditInput() {
    scheduleSave();
    if (typeof window.fitSheet1Type === "function") {
      window.requestAnimationFrame(window.fitSheet1Type);
    }
  }

  function onFocusIn(ev) {
    var td = ev.target.closest && ev.target.closest("td.ctor-editable");
    var tools = $("#ctor-table-tools");
    if (!tools) return;
    if (td) {
      tools.hidden = false;
      tools.dataset.tableId = syncTableId(td.closest("table"));
    } else if (!ev.target.closest("#ctor-table-tools")) {
      tools.hidden = true;
    }
  }

  function syncTableId(table) {
    if (!table) return "";
    if (!table.dataset.ctorId) {
      table.dataset.ctorId = "t" + Math.random().toString(36).slice(2, 9);
    }
    return table.dataset.ctorId;
  }

  function activeTable() {
    var tools = $("#ctor-table-tools");
    if (!tools || !tools.dataset.tableId) return null;
    return document.querySelector('table[data-ctor-id="' + tools.dataset.tableId + '"]');
  }

  function addTableRow() {
    var table = activeTable();
    if (!table || !table.tBodies.length) return;
    var body = table.tBodies[0];
    var ref = body.rows[body.rows.length - 1] || null;
    var cols = ref ? ref.cells.length : 2;
    var tr = document.createElement("tr");
    for (var i = 0; i < cols; i++) {
      var td = document.createElement("td");
      td.contentEditable = "true";
      td.className = "ctor-editable";
      td.textContent = "…";
      tr.appendChild(td);
    }
    body.appendChild(tr);
    scheduleSave();
  }

  function removeTableRow() {
    var table = activeTable();
    if (!table || !table.tBodies.length) return;
    var body = table.tBodies[0];
    if (body.rows.length <= 1) return;
    var focused = document.activeElement && document.activeElement.closest("tr");
    if (focused && body.contains(focused)) focused.remove();
    else body.deleteRow(body.rows.length - 1);
    scheduleSave();
  }

  function addTableCol() {
    var table = activeTable();
    if (!table || !table.tBodies.length) return;
    $all("tr", table).forEach(function (tr) {
      var td = document.createElement("td");
      td.contentEditable = "true";
      td.className = "ctor-editable";
      td.textContent = "…";
      tr.appendChild(td);
    });
    scheduleSave();
  }

  function removeTableCol() {
    var table = activeTable();
    if (!table || !table.tBodies.length) return;
    $all("tr", table).forEach(function (tr) {
      if (tr.cells.length <= 1) return;
      tr.deleteCell(tr.cells.length - 1);
    });
    scheduleSave();
  }

  function addSkuItem() {
    var list = $(".sku-list");
    if (!list) return;
    var li = document.createElement("li");
    li.contentEditable = "true";
    li.className = "ctor-editable";
    li.textContent = "SKU-…";
    list.appendChild(li);
    scheduleSave();
  }

  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 600);
    var st = $("#ctor-save-status");
    if (st) st.textContent = "не сохранено";
  }

  function saveDraft() {
    try {
      var stage = $(".stage");
      if (!stage) return;
      var payload = {
        savedAt: new Date().toISOString(),
        title: ($(".toolbar > strong") || {}).textContent || "",
        stageHtml: stage.innerHTML,
        bodyClass: document.body.className,
      };
      localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
      var st = $("#ctor-save-status");
      if (st) st.textContent = "черновик сохранён";
    } catch (err) {
      var st2 = $("#ctor-save-status");
      if (st2) st2.textContent = "ошибка сохранения (квота?)";
    }
  }

  function loadDraft() {
    try {
      var raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return false;
      var payload = JSON.parse(raw);
      var stage = $(".stage");
      if (!stage || !payload.stageHtml) return false;
      if (!window.confirm("Восстановить сохранённый черновик?")) return false;
      stage.innerHTML = payload.stageHtml;
      if (payload.title) {
        var strong = $(".toolbar > strong");
        if (strong) strong.textContent = payload.title;
      }
      return true;
    } catch (e) {
      return false;
    }
  }

  function clearDraft() {
    try {
      localStorage.removeItem(DRAFT_KEY);
    } catch (e) {
      /* ignore */
    }
  }

  function exportHtml() {
    var clone = document.documentElement.cloneNode(true);
    clone.querySelectorAll("#ctor-bar, #ctor-table-tools, .img-slot-label").forEach(function (n) {
      n.remove();
    });
    clone.querySelectorAll(".ctor-editable").forEach(function (el) {
      el.removeAttribute("contenteditable");
      el.classList.remove("ctor-editable");
    });
    clone.querySelectorAll(".img-slot.is-empty").forEach(function (slot) {
      slot.classList.remove("is-empty");
    });
    clone.querySelectorAll("[data-ctor-slot-bound], [data-ctor-id]").forEach(function (el) {
      el.removeAttribute("data-ctor-slot-bound");
      el.removeAttribute("data-ctor-id");
    });
    var ctorScripts = clone.querySelectorAll('script[src*="manual-constructor"]');
    ctorScripts.forEach(function (s) {
      s.remove();
    });
    clone.querySelectorAll("#ctor-bar, body").forEach(function () {});
    var body = clone.querySelector("body");
    if (body) {
      body.classList.remove("ctor-edit");
      body.removeAttribute("data-constructor");
      body.removeAttribute("data-constructor-kit");
    }
    var html = "<!DOCTYPE html>\n" + clone.outerHTML;
    var blob = new Blob([html], { type: "text/html;charset=utf-8" });
    var a = document.createElement("a");
    var name = (($(".toolbar > strong") || {}).textContent || "manual")
      .trim()
      .replace(/[^\wа-яё\-]+/gi, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60);
    a.href = URL.createObjectURL(blob);
    a.download = (name || "manual") + ".html";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function buildCtorBar() {
    if ($("#ctor-bar")) return;
    var bar = document.createElement("div");
    bar.id = "ctor-bar";
    bar.innerHTML =
      '<div class="ctor-bar-row">' +
      "<strong>Конструктор мануалов</strong>" +
      '<label class="ctor-field">Шаблон ' +
      '<select id="ctor-template"></select></label>' +
      '<button type="button" id="ctor-load-tpl" class="secondary">Загрузить шаблон</button>' +
      '<button type="button" id="ctor-restore" class="secondary">Черновик</button>' +
      '<button type="button" id="ctor-save" class="secondary">Сохранить</button>' +
      '<button type="button" id="ctor-export">Скачать HTML</button>' +
      '<button type="button" id="ctor-print" class="secondary">Печать / PDF</button>' +
      '<button type="button" id="ctor-add-sku" class="secondary">+ SKU</button>' +
      '<span id="ctor-save-status" class="ctor-status"></span>' +
      '<a href="index.html">каталог</a>' +
      '<a href="TEMPLATES.md">TEMPLATES</a>' +
      "</div>" +
      '<p class="ctor-hint">Режим правки: клик по тексту/ячейке — редактирование; клик по ' +
      "пунктирному слоту — вставить PNG; кроп — кнопка «Кроп фото» в тулбаре листа.</p>";
    document.body.insertBefore(bar, document.body.firstChild);

    var tools = document.createElement("div");
    tools.id = "ctor-table-tools";
    tools.hidden = true;
    tools.innerHTML =
      "<span>Таблица:</span>" +
      '<button type="button" data-act="row+">+ ряд</button>' +
      '<button type="button" data-act="row-" class="secondary">− ряд</button>' +
      '<button type="button" data-act="col+">+ кол.</button>' +
      '<button type="button" data-act="col-" class="secondary">− кол.</button>';
    document.body.appendChild(tools);

    var sel = $("#ctor-template");
    TEMPLATES.forEach(function (t) {
      var opt = document.createElement("option");
      opt.value = t.url;
      opt.textContent = t.label;
      if (/template-kit/.test(location.pathname) && t.id === "kit") opt.selected = true;
      sel.appendChild(opt);
    });

    $("#ctor-load-tpl").addEventListener("click", function () {
      var url = sel.value;
      if (!url) return;
      if (!window.confirm("Открыть выбранный шаблон в режиме конструктора? Сохраните черновик при необходимости.")) {
        return;
      }
      saveDraft();
      if (/template-kit\.html$/i.test(url) || url === "template-kit.html") {
        location.href = "constructor.html";
      } else {
        location.href = url + (url.indexOf("#") >= 0 ? "" : "#ctor");
      }
    });
    $("#ctor-restore").addEventListener("click", function () {
      if (loadDraft()) {
        bootEditor(false);
        var st = $("#ctor-save-status");
        if (st) st.textContent = "черновик загружен";
      }
    });
    $("#ctor-save").addEventListener("click", saveDraft);
    $("#ctor-export").addEventListener("click", exportHtml);
    $("#ctor-print").addEventListener("click", function () {
      window.print();
    });
    $("#ctor-add-sku").addEventListener("click", addSkuItem);
    tools.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-act]");
      if (!btn) return;
      var act = btn.getAttribute("data-act");
      if (act === "row+") addTableRow();
      if (act === "row-") removeTableRow();
      if (act === "col+") addTableCol();
      if (act === "col-") removeTableCol();
    });
  }

  function injectCtorStyles() {
    if ($("#ctor-styles")) return;
    var style = document.createElement("style");
    style.id = "ctor-styles";
    style.textContent =
      "#ctor-bar{position:fixed;left:0;right:0;top:0;z-index:40;" +
      "background:#1a1a1a;color:#fff;padding:8px 12px;font:12px/1.35 system-ui,sans-serif;" +
      "box-shadow:0 4px 16px rgba(0,0,0,.25)}" +
      "#ctor-bar a{color:#9cf;margin-left:8px}" +
      ".ctor-bar-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}" +
      ".ctor-field{display:inline-flex;gap:6px;align-items:center}" +
      "#ctor-bar select{max-width:220px}" +
      "#ctor-bar button,.ctor-field select{font:inherit}" +
      ".ctor-hint{margin:6px 0 0;color:#bbb;font-size:11px}" +
      ".ctor-status{color:#8d8;margin-left:4px}" +
      "body.ctor-edit{padding-top:72px}" +
      "body.ctor-edit .toolbar{top:72px}" +
      "#ctor-table-tools{position:fixed;right:12px;top:88px;z-index:35;" +
      "display:flex;gap:6px;align-items:center;padding:8px 10px;background:#111;color:#fff;" +
      "border-radius:8px;font:12px system-ui;box-shadow:0 6px 20px rgba(0,0,0,.3)}" +
      "#ctor-table-tools[hidden]{display:none!important}" +
      "#ctor-table-tools button{font:inherit;padding:4px 8px}" +
      ".img-slot{position:relative;cursor:pointer}" +
      ".img-slot.is-empty{outline:1.5px dashed #9aa;outline-offset:-2px;" +
      "background:repeating-linear-gradient(-45deg,#f7f7f7,#f7f7f7 6px,#efefef 6px,#efefef 12px);" +
      "min-height:24mm}" +
      ".img-slot .img-slot-label{display:none;position:absolute;inset:0;" +
      "align-items:center;justify-content:center;text-align:center;padding:3mm;" +
      "font-size:9pt;font-weight:600;color:#666;pointer-events:none;z-index:2}" +
      ".img-slot.is-empty .img-slot-label{display:flex}" +
      "body.ctor-edit .ctor-editable:focus{outline:2px solid #4a90d9;outline-offset:1px}" +
      "body.ctor-edit td.ctor-editable:focus{background:#eef5fc}" +
      "@media print{#ctor-bar,#ctor-table-tools,.img-slot-label{display:none!important}" +
      ".img-slot.is-empty{outline:none;background:#f3f3f3}}";
    document.head.appendChild(style);
  }

  function bootEditor(askDraft) {
    injectCtorStyles();
    buildCtorBar();
    document.body.setAttribute("data-constructor", "1");
    document.body.classList.add("ctor-edit");
    if (askDraft && localStorage.getItem(DRAFT_KEY)) {
      loadDraft();
    }
    markImgSlots();
    enableTextEditing();
    /* Re-bind crop after slots/images settle. */
    if (typeof window.hooconPhotoCropRefresh === "function") {
      window.setTimeout(window.hooconPhotoCropRefresh, 50);
    }
    var th = $("#ctor-bar");
    if (th) {
      document.body.style.setProperty("--ctor-bar-h", th.offsetHeight + "px");
    }
  }

  function start() {
    if (!isConstructorPage() && location.hash !== "#ctor") return;
    bootEditor(true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
