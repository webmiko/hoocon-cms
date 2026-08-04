/**
 * Per-image crop for RU manuals — screen + print PDF.
 *
 * Each content image gets its own crop rectangle (edges in % of the source),
 * zoom, and position (posX/posY, 50/50 = centre). Edges move both ways.
 *
 * Screen uses clip-path + transform. Firefox print often mis-renders that pair,
 * so beforeprint bakes the same geometry into a canvas bitmap (afterprint restores).
 *
 * Download PNG to bake into ``assets/<stem>/….png``, then «Сброс».
 */
(function () {
  "use strict";

  var EDGE_MIN = -25;
  var EDGE_MAX = 125;
  var MIN_SPAN = 8;
  var ZOOM_MIN = 50;
  var ZOOM_MAX = 200;
  var POS_MIN = 0;
  var POS_MAX = 100;

  /** Prefer specific classes; fall back to all stem asset PNGs in the sheets. */
  var SCAN_SELECTORS = [
    "img.product-photo",
    "img.lead-photo",
    "img.aux-diagram",
    ".unlock-media img",
    ".sheet1-unlock img",
    ".sheet1-dip-diagram img",
    ".wiring-board > img",
    ".diagram-rotation .rotation-panel > img",
    ".diagram-rotation .rotation-media > img",
    ".diagram-thermal img",
    ".diagram-dip > img",
    ".diagrams .diagram > img",
    ".diagrams .diagram img",
  ];

  function clamp(n, lo, hi) {
    n = Number(n);
    if (!isFinite(n)) return lo;
    if (n < lo) return lo;
    if (n > hi) return hi;
    return Math.round(n * 10) / 10;
  }

  function defaultRect() {
    return {
      left: 0,
      top: 0,
      right: 100,
      bottom: 100,
      zoom: 100,
      posX: 50,
      posY: 50,
    };
  }

  function normalizeRect(o) {
    var r = defaultRect();
    if (!o || typeof o !== "object") return r;
    r.left = clamp(o.left, EDGE_MIN, EDGE_MAX);
    r.top = clamp(o.top, EDGE_MIN, EDGE_MAX);
    r.right = clamp(o.right, EDGE_MIN, EDGE_MAX);
    r.bottom = clamp(o.bottom, EDGE_MIN, EDGE_MAX);
    r.zoom = clamp(o.zoom != null ? o.zoom : 100, ZOOM_MIN, ZOOM_MAX);
    r.posX = clamp(o.posX != null ? o.posX : 50, POS_MIN, POS_MAX);
    r.posY = clamp(o.posY != null ? o.posY : 50, POS_MIN, POS_MAX);
    if (r.right - r.left < MIN_SPAN) {
      r.right = clamp(r.left + MIN_SPAN, EDGE_MIN, EDGE_MAX);
      if (r.right - r.left < MIN_SPAN) {
        r.left = clamp(r.right - MIN_SPAN, EDGE_MIN, EDGE_MAX);
      }
    }
    if (r.bottom - r.top < MIN_SPAN) {
      r.bottom = clamp(r.top + MIN_SPAN, EDGE_MIN, EDGE_MAX);
      if (r.bottom - r.top < MIN_SPAN) {
        r.top = clamp(r.bottom - MIN_SPAN, EDGE_MIN, EDGE_MAX);
      }
    }
    return r;
  }

  function assetKey(img) {
    var slot = (img.getAttribute("data-slot") || "").trim();
    if (slot) return slot;
    var named = (img.getAttribute("data-filename") || "").trim();
    if (named) {
      return named.replace(/\.[^.]+$/, "") || named;
    }
    var src = img.getAttribute("src") || "";
    if (src.indexOf("data:") === 0) {
      if (img.classList.contains("product-photo")) return "product";
      if (img.classList.contains("lead-photo")) return "lead";
      if (img.classList.contains("aux-diagram")) return "aux-diagram";
      return "img-" + Array.prototype.indexOf.call(document.images, img);
    }
    var base = src.split("?")[0].split("/").pop() || "";
    if (base) return base.replace(/\.[^.]+$/, "") || base;
    if (img.classList.contains("product-photo")) return "product";
    if (img.classList.contains("lead-photo")) return "lead";
    return "img-" + Array.prototype.indexOf.call(document.images, img);
  }

  function labelFor(img, key) {
    if (img.classList.contains("product-photo")) return "product — лист 1";
    if (img.classList.contains("lead-photo")) return "lead — лист 2";
    if (img.classList.contains("aux-diagram")) return "aux — лист 1";
    if (key === "unlock" || img.closest(".unlock-media")) {
      return "unlock — разблокировка";
    }
    if (key.indexOf("wiring") === 0) return "wiring — схема";
    if (key.indexOf("dimension") === 0) return "dimensions — габариты";
    if (key.indexOf("rotation") === 0) return "rotation — направление";
    if (key.indexOf("thermal") === 0) return "thermal — SAF72";
    if (key.indexOf("dip") === 0) return "dip — переключатели";
    return key;
  }

  function discoverTargets() {
    var seen = Object.create(null);
    var list = [];
    SCAN_SELECTORS.forEach(function (sel) {
      document.querySelectorAll(sel).forEach(function (img) {
        if (!(img instanceof HTMLImageElement)) return;
        if (img.closest(".photo-crop-panel")) return;
        var src = img.getAttribute("src") || "";
        if (!src || /hoocon-logo/i.test(src)) return;
        if (img.hasAttribute("data-empty") || img.hidden) return;
        var key = assetKey(img);
        if (seen[key]) return;
        seen[key] = true;
        list.push({ key: key, img: img, label: labelFor(img, key) });
      });
    });
    return list;
  }

  function storageKey(key) {
    return "hoocon-manual-photo-crop:v5:" + location.pathname + ":" + key;
  }

  function loadRect(key) {
    try {
      var raw = localStorage.getItem(storageKey(key));
      if (!raw) return defaultRect();
      return normalizeRect(JSON.parse(raw));
    } catch (e) {
      return defaultRect();
    }
  }

  function saveRect(key, rect) {
    try {
      localStorage.setItem(storageKey(key), JSON.stringify(rect));
    } catch (e) {
      /* ignore */
    }
  }

  function isIdentity(rect) {
    return (
      rect.left === 0 &&
      rect.top === 0 &&
      rect.right === 100 &&
      rect.bottom === 100 &&
      rect.zoom === 100 &&
      (rect.posX == null || rect.posX === 50) &&
      (rect.posY == null || rect.posY === 50)
    );
  }

  function insetFromRect(rect) {
    return {
      top: rect.top,
      right: 100 - rect.right,
      bottom: 100 - rect.bottom,
      left: rect.left,
    };
  }

  function clipCss(rect) {
    var i = insetFromRect(rect);
    return (
      "inset(" +
      i.top +
      "% " +
      i.right +
      "% " +
      i.bottom +
      "% " +
      i.left +
      "%)"
    );
  }

  var MEDIA_SLOT_CLASSES = [
    "product-media",
    "aux-diagram-media",
    "unlock-media",
    "summary-media",
    "sheet1-dip-diagram",
    "wiring-board",
    "rotation-media",
  ];

  function isMediaSlot(el) {
    if (!el || !el.classList) return false;
    for (var i = 0; i < MEDIA_SLOT_CLASSES.length; i++) {
      if (el.classList.contains(MEDIA_SLOT_CLASSES[i])) return true;
    }
    /* DA/SA product hero is bare .media inside .product-col */
    if (
      el.classList.contains("media") &&
      el.closest &&
      el.closest(".product-col")
    ) {
      return true;
    }
    return false;
  }

  function ensureWrap(img) {
    var parent = img.parentElement;
    /* Media slots: crop on the slot itself — no extra wrapper (clips like product). */
    if (parent && parent.classList.contains("photo-crop-wrap")) {
      var grand = parent.parentElement;
      if (grand && isMediaSlot(grand)) {
        grand.insertBefore(img, parent);
        parent.remove();
        return grand;
      }
      return parent;
    }
    if (parent && isMediaSlot(parent)) {
      return parent;
    }
    var slot = null;
    if (img.closest) {
      for (var i = 0; i < MEDIA_SLOT_CLASSES.length; i++) {
        slot = img.closest("." + MEDIA_SLOT_CLASSES[i]);
        if (slot) break;
      }
      if (!slot) {
        var pc = img.closest(".product-col > .media, .product-col .media");
        if (pc && isMediaSlot(pc)) slot = pc;
      }
    }
    if (slot && img.parentElement === slot) {
      return slot;
    }
    var wrap = document.createElement("div");
    wrap.className = "photo-crop-wrap";
    parent.insertBefore(wrap, img);
    wrap.appendChild(img);
    return wrap;
  }

  function applyCrop(img, rect) {
    if (!img) return;
    var wrap = ensureWrap(img);
    var empty = isIdentity(rect);
    wrap.classList.toggle("photo-crop-active", !empty);
    if (isMediaSlot(wrap)) {
      wrap.style.overflow = "hidden";
    }
    if (empty) {
      img.style.clipPath = "";
      img.style.webkitClipPath = "";
      img.style.transform = "";
      img.style.transformOrigin = "";
      img.removeAttribute("data-photo-crop");
      if (typeof window.syncPhotoBoundsGuide === "function") {
        try {
          window.syncPhotoBoundsGuide();
        } catch (err) {
          /* ignore */
        }
      }
      return;
    }
    var css = clipCss(rect);
    img.style.clipPath = css;
    img.style.webkitClipPath = css;
    var z = rect.zoom / 100;
    var posX = rect.posX != null ? rect.posX : 50;
    var posY = rect.posY != null ? rect.posY : 50;
    /* 50/50 = centre; 0 = left/top, 100 = right/bottom. */
    var tx = (posX - 50) * 2;
    var ty = (posY - 50) * 2;
    var parts = [];
    if (Math.abs(tx) > 0.05 || Math.abs(ty) > 0.05) {
      parts.push("translate(" + tx + "%, " + ty + "%)");
    }
    if (Math.abs(z - 1) > 0.001) {
      parts.push("scale(" + z + ")");
    }
    img.style.transform = parts.length ? parts.join(" ") : "";
    img.style.transformOrigin = "center center";
    img.setAttribute(
      "data-photo-crop",
      [rect.left, rect.top, rect.right, rect.bottom, rect.zoom, posX, posY].join(","),
    );

    if (typeof window.syncPhotoBoundsGuide === "function") {
      try {
        window.syncPhotoBoundsGuide();
      } catch (err) {
        /* ignore */
      }
    }
  }

  /**
   * Paint screen-equivalent crop into a slot-sized canvas (object-fit:contain
   * + clip-path inset + translate/scale from centre). Used for Firefox print.
   */
  function renderCropIntoSlotCanvas(img, rect, sw, sh) {
    if (!img || !img.naturalWidth || !img.naturalHeight) return null;
    if (!(sw > 0) || !(sh > 0)) return null;
    var dpr = 2;
    var cw = Math.max(1, Math.round(sw * dpr));
    var ch = Math.max(1, Math.round(sh * dpr));
    var canvas = document.createElement("canvas");
    canvas.width = cw;
    canvas.height = ch;
    var ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, cw, ch);

    var nw = img.naturalWidth;
    var nh = img.naturalHeight;
    var fit = Math.min(cw / nw, ch / nh);
    var dw = nw * fit;
    var dh = nh * fit;
    var ox = (cw - dw) / 2;
    var oy = (ch - dh) / 2;

    var z = (rect.zoom != null ? rect.zoom : 100) / 100;
    var posX = rect.posX != null ? rect.posX : 50;
    var posY = rect.posY != null ? rect.posY : 50;
    /* Match applyCrop: translate((pos-50)*2%, …) scale(z), origin centre. */
    var tx = (((posX - 50) * 2) / 100) * dw;
    var ty = (((posY - 50) * 2) / 100) * dh;
    var inset = insetFromRect(rect);
    var cx = ox + dw / 2;
    var cy = oy + dh / 2;

    try {
      ctx.save();
      /* CSS: transform then clip together — path coords follow CTM. */
      ctx.translate(cx, cy);
      ctx.translate(tx, ty);
      ctx.scale(z, z);
      ctx.translate(-cx, -cy);
      ctx.beginPath();
      ctx.rect(
        ox + (dw * inset.left) / 100,
        oy + (dh * inset.top) / 100,
        (dw * (100 - inset.left - inset.right)) / 100,
        (dh * (100 - inset.top - inset.bottom)) / 100,
      );
      ctx.clip();
      ctx.drawImage(img, ox, oy, dw, dh);
      ctx.restore();
    } catch (err) {
      return null;
    }
    return canvas;
  }

  function slotSizeFor(img) {
    var wrap = ensureWrap(img);
    var r = wrap.getBoundingClientRect();
    if (r.width >= 4 && r.height >= 4) {
      return { w: r.width, h: r.height };
    }
    return {
      w: img.clientWidth || img.naturalWidth || 400,
      h: img.clientHeight || img.naturalHeight || 400,
    };
  }

  var printBakeRestore = [];

  function clearPrintBakeStyles(img) {
    img.style.clipPath = "";
    img.style.webkitClipPath = "";
    img.style.transform = "";
    img.style.transformOrigin = "";
    img.style.width = "";
    img.style.height = "";
    img.style.maxWidth = "";
    img.style.maxHeight = "";
    img.style.objectFit = "";
    img.style.objectPosition = "";
    img.style.position = "";
    img.style.left = "";
    img.style.top = "";
  }

  function bakeCropsForPrint(targets, state) {
    restoreCropsAfterPrint();
    targets.forEach(function (t) {
      var rect = state[t.key];
      if (!rect || isIdentity(rect)) return;
      var img = t.img;
      if (!img || !img.naturalWidth) return;
      var slot = slotSizeFor(img);
      var canvas = renderCropIntoSlotCanvas(img, rect, slot.w, slot.h);
      if (!canvas) return;
      /* Insert painted canvas — no async decode race on img.src data-URL. */
      canvas.setAttribute("aria-hidden", "true");
      canvas.className = (img.className || "") + " photo-crop-print-bake";
      canvas.style.display = "block";
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      canvas.style.maxWidth = "100%";
      canvas.style.maxHeight = "100%";
      canvas.style.objectFit = "fill";
      canvas.style.clipPath = "none";
      canvas.style.transform = "none";
      if (!img.parentNode) return;
      img.parentNode.insertBefore(canvas, img);
      img.style.display = "none";
      printBakeRestore.push({
        img: img,
        canvas: canvas,
        rect: rect,
      });
    });
  }

  function restoreCropsAfterPrint() {
    if (!printBakeRestore.length) return;
    var pending = printBakeRestore.slice();
    printBakeRestore = [];
    pending.forEach(function (row) {
      var img = row.img;
      if (row.canvas && row.canvas.parentNode) {
        row.canvas.parentNode.removeChild(row.canvas);
      }
      if (!img) return;
      img.style.display = "";
      clearPrintBakeStyles(img);
      applyCrop(img, row.rect);
    });
  }

  function downloadCroppedPng(img, key, rect) {
    if (!img || !img.naturalWidth) {
      window.alert("Нет фото или оно ещё не загрузилось.");
      return;
    }
    var slot = slotSizeFor(img);
    var canvas = renderCropIntoSlotCanvas(img, rect, slot.w, slot.h);
    if (!canvas) {
      window.alert(
        "Не удалось вырезать PNG (CORS). Откройте мануал через http.server, не file://.",
      );
      return;
    }
    canvas.toBlob(function (blob) {
      if (!blob) return;
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = key + "-cropped.png";
      a.click();
      URL.revokeObjectURL(a.href);
    }, "image/png");
  }

  function migrateLegacy(key, img) {
    /* Old tool stored inset % for product/lead only. */
    if (key !== "product" && key !== "lead") return null;
    try {
      var legacy =
        "hoocon-manual-photo-crop:" + location.pathname + ":" + key;
      var raw = localStorage.getItem(legacy);
      if (!raw) return null;
      var o = JSON.parse(raw);
      return normalizeRect({
        left: o.left || 0,
        top: o.top || 0,
        right: 100 - (o.right || 0),
        bottom: 100 - (o.bottom || 0),
        zoom: 100,
      });
    } catch (e) {
      return null;
    }
  }

  function buildPanel() {
    var toolbar = document.querySelector(".toolbar");
    if (!toolbar || document.getElementById("photo-crop-panel")) return;

    var targets = discoverTargets();
    if (!targets.length) return;

    var btn = document.createElement("button");
    btn.type = "button";
    btn.id = "toggle-photo-crop";
    btn.className = "secondary";
    btn.setAttribute("aria-pressed", "false");
    btn.textContent = "Кроп фото";
    toolbar.appendChild(btn);

    var options = targets
      .map(function (t) {
        return (
          '<option value="' +
          t.key.replace(/"/g, "&quot;") +
          '">' +
          t.label.replace(/</g, "&lt;") +
          "</option>"
        );
      })
      .join("");

    var panel = document.createElement("aside");
    panel.id = "photo-crop-panel";
    panel.className = "photo-crop-panel";
    panel.hidden = true;
    panel.innerHTML =
      '<div class="photo-crop-drag" id="photo-crop-drag" title="Перетащить панель">' +
      "<strong>Кроп по изображению</strong>" +
      '<span class="photo-crop-drag-hint">⋮⋮</span></div>' +
      '<p class="photo-crop-hint">Края (−25…125%) — окно в исходнике. ' +
      "<em>Позиция</em> 50/50 = центр; 0=лево/верх, 100=право/низ. " +
      "«Центр» — сразу 50/50. " +
      "Масштаб &lt;100% — поля, &gt;100% — крупнее. " +
      "Запечь: «Скачать PNG» → файл → «Сброс». " +
      "Панель <em>перетаскивается</em> за заголовок.</p>" +
      '<label class="photo-crop-row photo-crop-target-row">Картинка ' +
      '<select id="photo-crop-target">' +
      options +
      "</select></label>" +
      '<label class="photo-crop-row">Верх ' +
      '<input type="range" min="-25" max="92" step="0.5" data-edge="top" />' +
      '<span data-val="top">0</span>%</label>' +
      '<label class="photo-crop-row">Низ ' +
      '<input type="range" min="8" max="125" step="0.5" data-edge="bottom" />' +
      '<span data-val="bottom">100</span>%</label>' +
      '<label class="photo-crop-row">Лево ' +
      '<input type="range" min="-25" max="92" step="0.5" data-edge="left" />' +
      '<span data-val="left">0</span>%</label>' +
      '<label class="photo-crop-row">Право ' +
      '<input type="range" min="8" max="125" step="0.5" data-edge="right" />' +
      '<span data-val="right">100</span>%</label>' +
      '<label class="photo-crop-row">Масштаб ' +
      '<input type="range" min="50" max="200" step="1" data-edge="zoom" />' +
      '<span data-val="zoom">100</span>%</label>' +
      '<label class="photo-crop-row">Гор. поз. ' +
      '<input type="range" min="0" max="100" step="1" data-edge="posX" />' +
      '<span data-val="posX">50</span>%</label>' +
      '<label class="photo-crop-row">Верт. поз. ' +
      '<input type="range" min="0" max="100" step="1" data-edge="posY" />' +
      '<span data-val="posY">50</span>%</label>' +
      '<code class="photo-crop-css" id="photo-crop-css"></code>' +
      '<div class="photo-crop-actions">' +
      '<button type="button" id="photo-crop-center" class="secondary" ' +
      'title="Гор. и верт. позиция → 50/50 (центр контейнера)">' +
      "Центр</button>" +
      '<button type="button" id="photo-crop-reset" class="secondary">Сброс</button>' +
      '<button type="button" id="photo-crop-download">Скачать PNG</button>' +
      "</div>";
    document.body.appendChild(panel);

    var style = document.getElementById("photo-crop-tool-style");
    if (!style) {
      style = document.createElement("style");
      style.id = "photo-crop-tool-style";
      style.textContent =
      ".photo-crop-panel{" +
      "position:fixed;right:12px;bottom:12px;z-index:30;" +
      "width:min(340px,calc(100vw - 24px));padding:0 14px 12px;" +
      "background:#111;color:#fff;border-radius:8px;" +
      "box-shadow:0 8px 28px rgba(0,0,0,.35);font-size:12px;" +
      "display:flex;flex-direction:column;gap:8px;max-height:min(70vh,560px);" +
      "overflow:auto}" +
      ".photo-crop-panel[hidden]{display:none!important}" +
      ".photo-crop-drag{display:flex;align-items:center;justify-content:space-between;" +
      "gap:8px;margin:0 -14px;padding:10px 14px 8px;cursor:grab;" +
      "user-select:none;touch-action:none;border-radius:8px 8px 0 0;background:#1a1a1a;" +
      "border-bottom:1px solid #333;position:sticky;top:0;z-index:1}" +
      ".photo-crop-drag:active,.photo-crop-panel.photo-crop-dragging .photo-crop-drag{" +
      "cursor:grabbing}" +
      ".photo-crop-panel.photo-crop-dragging{opacity:.96;" +
      "box-shadow:0 12px 36px rgba(0,0,0,.45)}" +
      ".photo-crop-drag strong{font-size:13px}" +
      ".photo-crop-drag-hint{color:#888;letter-spacing:-2px;font-size:14px}" +
      ".photo-crop-hint{margin:0;color:#bbb;line-height:1.35}" +
      ".photo-crop-hint code{color:#9cf;font-size:11px}" +
      ".photo-crop-hint em{color:#eee;font-style:normal}" +
      ".photo-crop-row{display:grid;grid-template-columns:72px 1fr 44px;" +
      "gap:8px;align-items:center}" +
      ".photo-crop-target-row{grid-template-columns:72px 1fr}" +
      ".photo-crop-target-row select{width:100%;font-size:12px}" +
      ".photo-crop-row input[type=range]{width:100%}" +
      ".photo-crop-css{display:block;padding:6px 8px;background:#222;" +
      "border-radius:4px;font-size:11px;word-break:break-all;color:#9cf}" +
      ".photo-crop-actions{display:flex;gap:8px;flex-wrap:wrap}" +
      ".photo-crop-actions button{flex:1}" +
      ".photo-crop-wrap{overflow:hidden;display:block;max-width:100%;" +
      "line-height:0;height:100%}" +
      ".product-col .product-media,.product-col .media," +
      ".aux-diagram-media,.unlock-media,.summary-media," +
      ".sheet1-dip-diagram,.wiring-board,.diagram," +
      ".rotation-media{overflow:hidden;isolation:isolate}" +
      ".photo-crop-wrap > img,.product-media > img,.product-col .media > img," +
      ".aux-diagram-media > img,.summary-media > img," +
      ".unlock-media img,.wiring-board > img,.diagram > img{" +
      "max-width:100%;max-height:100%;width:auto;height:auto;" +
      "object-fit:contain;" +
      "transition:clip-path .05s linear,transform .05s linear}" +
      ".media .photo-crop-wrap,.summary-media .photo-crop-wrap," +
      ".aux-diagram-media .photo-crop-wrap," +
      ".unlock-media .photo-crop-wrap," +
      ".wiring-board .photo-crop-wrap," +
      ".diagram .photo-crop-wrap," +
      ".rotation-panel .photo-crop-wrap," +
      ".rotation-media .photo-crop-wrap{width:100%;height:100%}" +
      ".sheet1-unlock .unlock-media > .photo-crop-wrap{" +
      "grid-column:4 / span 3;width:100%;min-width:0;max-height:40mm;" +
      "justify-self:stretch}" +
      "@media print{.photo-crop-panel,#toggle-photo-crop{display:none!important}}";
      document.head.appendChild(style);
    }
    var byKey = Object.create(null);
    targets.forEach(function (t) {
      byKey[t.key] = t;
    });

    var state = Object.create(null);
    targets.forEach(function (t) {
      var loaded = loadRect(t.key);
      if (isIdentity(loaded)) {
        var legacy = migrateLegacy(t.key, t.img);
        if (legacy) loaded = legacy;
      }
      state[t.key] = loaded;
      applyCrop(t.img, loaded);
      saveRect(t.key, loaded);
    });

    function currentKey() {
      return document.getElementById("photo-crop-target").value;
    }

    function currentTarget() {
      return byKey[currentKey()];
    }

    function syncInputs() {
      var key = currentKey();
      var rect = state[key];
      panel.querySelectorAll("input[data-edge]").forEach(function (input) {
        var edge = input.getAttribute("data-edge");
        input.value = String(rect[edge]);
        var span = panel.querySelector('[data-val="' + edge + '"]');
        if (span) span.textContent = String(rect[edge]);
      });
      var i = insetFromRect(rect);
      document.getElementById("photo-crop-css").textContent =
        "окно " +
        rect.left +
        "–" +
        rect.right +
        "% × " +
        rect.top +
        "–" +
        rect.bottom +
        "% · zoom " +
        rect.zoom +
        "% · поз " +
        rect.posX +
        "/" +
        rect.posY +
        " · " +
        clipCss(rect);
      void i;
    }

    function readInputs() {
      var key = currentKey();
      var rect = state[key];
      var draft = {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        zoom: rect.zoom,
        posX: rect.posX,
        posY: rect.posY,
      };
      panel.querySelectorAll("input[data-edge]").forEach(function (input) {
        var edge = input.getAttribute("data-edge");
        draft[edge] = Number(input.value);
      });
      // Keep opposite edges from crossing.
      if (draft.left > draft.right - MIN_SPAN) {
        if (panel.querySelector('input[data-edge="left"]') === document.activeElement) {
          draft.right = clamp(draft.left + MIN_SPAN, EDGE_MIN, EDGE_MAX);
        } else {
          draft.left = clamp(draft.right - MIN_SPAN, EDGE_MIN, EDGE_MAX);
        }
      }
      if (draft.top > draft.bottom - MIN_SPAN) {
        if (panel.querySelector('input[data-edge="top"]') === document.activeElement) {
          draft.bottom = clamp(draft.top + MIN_SPAN, EDGE_MIN, EDGE_MAX);
        } else {
          draft.top = clamp(draft.bottom - MIN_SPAN, EDGE_MIN, EDGE_MAX);
        }
      }
      rect = normalizeRect(draft);
      state[key] = rect;
      var t = currentTarget();
      if (t) applyCrop(t.img, rect);
      saveRect(key, rect);
      syncInputs();
    }

    syncInputs();

    var PANEL_POS_KEY = "hoocon-manual-photo-crop:panel-pos";

    function clampPanelPos(left, top) {
      var pad = 8;
      var w = panel.offsetWidth || 340;
      var h = panel.offsetHeight || 200;
      var maxL = Math.max(pad, window.innerWidth - w - pad);
      var maxT = Math.max(pad, window.innerHeight - h - pad);
      return {
        left: Math.min(maxL, Math.max(pad, left)),
        top: Math.min(maxT, Math.max(pad, top)),
      };
    }

    function applyPanelPos(pos) {
      if (!pos) return;
      var p = clampPanelPos(pos.left, pos.top);
      panel.style.left = p.left + "px";
      panel.style.top = p.top + "px";
      panel.style.right = "auto";
      panel.style.bottom = "auto";
    }

    function savePanelPos() {
      try {
        localStorage.setItem(
          PANEL_POS_KEY,
          JSON.stringify({
            left: parseFloat(panel.style.left) || 0,
            top: parseFloat(panel.style.top) || 0,
          }),
        );
      } catch (e) {
        /* ignore */
      }
    }

    function loadPanelPos() {
      try {
        var raw = localStorage.getItem(PANEL_POS_KEY);
        if (!raw) return null;
        var o = JSON.parse(raw);
        if (typeof o.left !== "number" || typeof o.top !== "number") return null;
        return o;
      } catch (e) {
        return null;
      }
    }

    function enablePanelDrag() {
      var handle = document.getElementById("photo-crop-drag");
      if (!handle) return;
      var dragging = false;
      var startX = 0;
      var startY = 0;
      var origL = 0;
      var origT = 0;

      function onMove(clientX, clientY) {
        if (!dragging) return;
        applyPanelPos({
          left: origL + (clientX - startX),
          top: origT + (clientY - startY),
        });
      }

      function onUp() {
        if (!dragging) return;
        dragging = false;
        panel.classList.remove("photo-crop-dragging");
        savePanelPos();
        document.removeEventListener("pointermove", onPointerMove);
        document.removeEventListener("pointerup", onPointerUp);
        document.removeEventListener("pointercancel", onPointerUp);
      }

      function onPointerMove(ev) {
        onMove(ev.clientX, ev.clientY);
      }

      function onPointerUp() {
        onUp();
      }

      handle.addEventListener("pointerdown", function (ev) {
        if (ev.button != null && ev.button !== 0) return;
        var rect = panel.getBoundingClientRect();
        dragging = true;
        startX = ev.clientX;
        startY = ev.clientY;
        origL = rect.left;
        origT = rect.top;
        panel.classList.add("photo-crop-dragging");
        applyPanelPos({ left: origL, top: origT });
        try {
          handle.setPointerCapture(ev.pointerId);
        } catch (e) {
          /* ignore */
        }
        document.addEventListener("pointermove", onPointerMove);
        document.addEventListener("pointerup", onPointerUp);
        document.addEventListener("pointercancel", onPointerUp);
        ev.preventDefault();
      });

      window.addEventListener("resize", function () {
        if (!panel.style.left) return;
        applyPanelPos({
          left: parseFloat(panel.style.left) || 0,
          top: parseFloat(panel.style.top) || 0,
        });
        savePanelPos();
      });
    }

    enablePanelDrag();
    var savedPos = loadPanelPos();
    if (savedPos) applyPanelPos(savedPos);

    btn.addEventListener("click", function () {
      var open = panel.hidden;
      panel.hidden = !open;
      btn.setAttribute("aria-pressed", open ? "true" : "false");
    });

    document
      .getElementById("photo-crop-target")
      .addEventListener("change", syncInputs);
    panel.querySelectorAll("input[data-edge]").forEach(function (input) {
      input.addEventListener("input", readInputs);
    });
    document.getElementById("photo-crop-center").addEventListener("click", function () {
      var key = currentKey();
      var prev = state[key];
      var rect = normalizeRect({
        left: prev.left,
        top: prev.top,
        right: prev.right,
        bottom: prev.bottom,
        zoom: prev.zoom,
        posX: 50,
        posY: 50,
      });
      state[key] = rect;
      var t = currentTarget();
      if (t) applyCrop(t.img, rect);
      saveRect(key, rect);
      syncInputs();
    });
    document.getElementById("photo-crop-reset").addEventListener("click", function () {
      var key = currentKey();
      state[key] = defaultRect();
      var t = currentTarget();
      if (t) applyCrop(t.img, state[key]);
      saveRect(key, state[key]);
      syncInputs();
    });
    document
      .getElementById("photo-crop-download")
      .addEventListener("click", function () {
        var key = currentKey();
        var t = currentTarget();
        if (!t) return;
        downloadCroppedPng(t.img, key, state[key]);
      });

    /* Firefox: clip-path+transform on <img> ≠ screen in print/PDF. Bake bitmaps. */
    bakeForPrintImpl = function () {
      bakeCropsForPrint(targets, state);
    };
    if (!printHooksBound) {
      printHooksBound = true;
      window.addEventListener("beforeprint", function () {
        if (bakeForPrintImpl) bakeForPrintImpl();
      });
      window.addEventListener("afterprint", restoreCropsAfterPrint);
      if (typeof window.matchMedia === "function") {
        var printMql = window.matchMedia("print");
        var onPrintMql = function (mql) {
          if (mql.matches) {
            if (bakeForPrintImpl) bakeForPrintImpl();
          } else {
            restoreCropsAfterPrint();
          }
        };
        if (typeof printMql.addEventListener === "function") {
          printMql.addEventListener("change", onPrintMql);
        } else if (typeof printMql.addListener === "function") {
          printMql.addListener(onPrintMql);
        }
      }
    }
  }

  var bakeForPrintImpl = null;
  var printHooksBound = false;

  function rebuildPhotoCropPanel() {
    var oldPanel = document.getElementById("photo-crop-panel");
    if (oldPanel) oldPanel.remove();
    var oldBtn = document.getElementById("toggle-photo-crop");
    if (oldBtn) oldBtn.remove();
    restoreCropsAfterPrint();
    buildPanel();
  }

  window.hooconPhotoCropRefresh = rebuildPhotoCropPanel;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildPanel);
  } else {
    buildPanel();
  }
})();
