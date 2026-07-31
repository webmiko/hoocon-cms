/**
 * Manual photo crop for product/lead — screen + print PDF.
 *
 * Sliders set inset % on the image (clip-path). Same crop is used when
 * printing to PDF. Optional download of a baked PNG to replace the asset.
 */
(function () {
  "use strict";

  var TARGETS = {
    product: { sel: ".product-photo", label: "product (лист 1)" },
    lead: { sel: ".lead-photo", label: "lead (лист 2)" },
  };

  function storageKey(kind) {
    return "hoocon-manual-photo-crop:" + location.pathname + ":" + kind;
  }

  function loadEdges(kind) {
    try {
      var raw = localStorage.getItem(storageKey(kind));
      if (!raw) return { top: 0, right: 0, bottom: 0, left: 0 };
      var o = JSON.parse(raw);
      return {
        top: clamp(o.top),
        right: clamp(o.right),
        bottom: clamp(o.bottom),
        left: clamp(o.left),
      };
    } catch (e) {
      return { top: 0, right: 0, bottom: 0, left: 0 };
    }
  }

  function saveEdges(kind, edges) {
    try {
      localStorage.setItem(storageKey(kind), JSON.stringify(edges));
    } catch (e) {
      /* ignore quota / private mode */
    }
  }

  function clamp(n) {
    n = Number(n) || 0;
    if (n < 0) return 0;
    if (n > 45) return 45;
    return Math.round(n * 10) / 10;
  }

  function insetCss(edges) {
    return (
      "inset(" +
      edges.top +
      "% " +
      edges.right +
      "% " +
      edges.bottom +
      "% " +
      edges.left +
      "%)"
    );
  }

  function applyCrop(kind, edges) {
    var img = document.querySelector(TARGETS[kind].sel);
    if (!img) return;
    var empty =
      edges.top === 0 &&
      edges.right === 0 &&
      edges.bottom === 0 &&
      edges.left === 0;
    if (empty) {
      img.style.clipPath = "";
      img.style.webkitClipPath = "";
      img.removeAttribute("data-photo-crop");
    } else {
      var css = insetCss(edges);
      img.style.clipPath = css;
      img.style.webkitClipPath = css;
      img.setAttribute(
        "data-photo-crop",
        [edges.top, edges.right, edges.bottom, edges.left].join(","),
      );
    }
    var box = img.closest(".media, .summary-media");
    if (box) {
      box.classList.toggle("photo-crop-active", !empty);
    }
    saveEdges(kind, edges);
  }

  function downloadCroppedPng(kind, edges) {
    var img = document.querySelector(TARGETS[kind].sel);
    if (!img || !img.naturalWidth) {
      window.alert("Нет фото или оно ещё не загрузилось.");
      return;
    }
    var nw = img.naturalWidth;
    var nh = img.naturalHeight;
    var x0 = Math.round((nw * edges.left) / 100);
    var y0 = Math.round((nh * edges.top) / 100);
    var x1 = Math.round(nw * (1 - edges.right / 100));
    var y1 = Math.round(nh * (1 - edges.bottom / 100));
    var w = Math.max(1, x1 - x0);
    var h = Math.max(1, y1 - y0);
    var canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, w, h);
    try {
      ctx.drawImage(img, x0, y0, w, h, 0, 0, w, h);
    } catch (err) {
      window.alert(
        "Не удалось вырезать PNG (CORS). Откройте мануал через http.server, не file://.",
      );
      return;
    }
    var src = img.getAttribute("src") || kind + ".png";
    var base = src.split("/").pop().replace(/\.[^.]+$/, "") || kind;
    canvas.toBlob(function (blob) {
      if (!blob) return;
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = base + "-cropped.png";
      a.click();
      URL.revokeObjectURL(a.href);
    }, "image/png");
  }

  function buildPanel() {
    var toolbar = document.querySelector(".toolbar");
    if (!toolbar || document.getElementById("photo-crop-panel")) return;

    var btn = document.createElement("button");
    btn.type = "button";
    btn.id = "toggle-photo-crop";
    btn.className = "secondary";
    btn.setAttribute("aria-pressed", "false");
    btn.textContent = "Кроп фото";
    toolbar.appendChild(btn);

    var panel = document.createElement("aside");
    panel.id = "photo-crop-panel";
    panel.className = "photo-crop-panel";
    panel.hidden = true;
    panel.innerHTML =
      "<strong>Кроп фото → печать PDF</strong>" +
      '<p class="photo-crop-hint">Границы срезаются и на экране, и в «Печать / PDF». ' +
      "Чтобы запечь в файл ассета: скачайте PNG и замените " +
      "<code>assets/…/product.png</code> или <code>lead.png</code>, затем «Сброс».</p>" +
      '<label class="photo-crop-row">Цель ' +
      '<select id="photo-crop-target">' +
      '<option value="product">product (лист 1)</option>' +
      '<option value="lead">lead (лист 2)</option>' +
      "</select></label>" +
      '<label class="photo-crop-row">Сверху ' +
      '<input type="range" min="0" max="45" step="0.5" data-edge="top" />' +
      '<span data-val="top">0</span>%</label>' +
      '<label class="photo-crop-row">Справа ' +
      '<input type="range" min="0" max="45" step="0.5" data-edge="right" />' +
      '<span data-val="right">0</span>%</label>' +
      '<label class="photo-crop-row">Снизу ' +
      '<input type="range" min="0" max="45" step="0.5" data-edge="bottom" />' +
      '<span data-val="bottom">0</span>%</label>' +
      '<label class="photo-crop-row">Слева ' +
      '<input type="range" min="0" max="45" step="0.5" data-edge="left" />' +
      '<span data-val="left">0</span>%</label>' +
      '<code class="photo-crop-css" id="photo-crop-css"></code>' +
      '<div class="photo-crop-actions">' +
      '<button type="button" id="photo-crop-reset" class="secondary">Сброс</button>' +
      '<button type="button" id="photo-crop-download">Скачать PNG</button>' +
      "</div>";
    document.body.appendChild(panel);

    var style = document.createElement("style");
    style.textContent =
      ".photo-crop-panel{" +
      "position:fixed;right:12px;bottom:12px;z-index:30;" +
      "width:min(320px,calc(100vw - 24px));padding:12px 14px;" +
      "background:#111;color:#fff;border-radius:8px;" +
      "box-shadow:0 8px 28px rgba(0,0,0,.35);font-size:12px;" +
      "display:flex;flex-direction:column;gap:8px}" +
      ".photo-crop-panel[hidden]{display:none!important}" +
      ".photo-crop-hint{margin:0;color:#bbb;line-height:1.35}" +
      ".photo-crop-hint code{color:#9cf;font-size:11px}" +
      ".photo-crop-row{display:grid;grid-template-columns:64px 1fr 40px;" +
      "gap:8px;align-items:center}" +
      ".photo-crop-row input[type=range]{width:100%}" +
      ".photo-crop-css{display:block;padding:6px 8px;background:#222;" +
      "border-radius:4px;font-size:11px;word-break:break-all;color:#9cf}" +
      ".photo-crop-actions{display:flex;gap:8px;flex-wrap:wrap}" +
      ".photo-crop-actions button{flex:1}" +
      ".media.photo-crop-active,.summary-media.photo-crop-active{" +
      "overflow:hidden}" +
      ".product-photo,.lead-photo{transition:clip-path .05s linear}" +
      "@media print{.photo-crop-panel,#toggle-photo-crop{display:none!important}}";
    document.head.appendChild(style);

    var state = {
      product: loadEdges("product"),
      lead: loadEdges("lead"),
    };

    function currentKind() {
      return document.getElementById("photo-crop-target").value;
    }

    function syncInputs() {
      var kind = currentKind();
      var edges = state[kind];
      panel.querySelectorAll("input[data-edge]").forEach(function (input) {
        var edge = input.getAttribute("data-edge");
        input.value = String(edges[edge]);
        var span = panel.querySelector('[data-val="' + edge + '"]');
        if (span) span.textContent = String(edges[edge]);
      });
      document.getElementById("photo-crop-css").textContent =
        "clip-path: " + insetCss(edges) + ";";
    }

    function readInputs() {
      var kind = currentKind();
      var edges = state[kind];
      panel.querySelectorAll("input[data-edge]").forEach(function (input) {
        var edge = input.getAttribute("data-edge");
        edges[edge] = clamp(input.value);
      });
      applyCrop(kind, edges);
      syncInputs();
    }

    Object.keys(TARGETS).forEach(function (kind) {
      applyCrop(kind, state[kind]);
    });
    syncInputs();

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
    document.getElementById("photo-crop-reset").addEventListener("click", function () {
      var kind = currentKind();
      state[kind] = { top: 0, right: 0, bottom: 0, left: 0 };
      applyCrop(kind, state[kind]);
      syncInputs();
    });
    document
      .getElementById("photo-crop-download")
      .addEventListener("click", function () {
        var kind = currentKind();
        downloadCroppedPng(kind, state[kind]);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildPanel);
  } else {
    buildPanel();
  }
})();
