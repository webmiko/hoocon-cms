/**
 * Support conversation messenger (Admin change form).
 * Enter sends; Shift+Enter inserts a newline.
 * Polls for new messages so staff see client replies without F5.
 */
(function () {
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  function scrollThread(thread) {
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  /**
   * Phone thread is position:fixed inset:0 — attached to the *layout* viewport.
   * When the on-screen keyboard opens, iOS/Android pan the visual viewport so
   * the header slides off-screen top and the composer sinks under the keyboard.
   * Pin the sheet to window.visualViewport so header + composer stay visible.
   */
  function setupViewportPin(root, thread, textarea) {
    var vv = window.visualViewport;
    if (!root || !vv) return;

    function isFixedLayout() {
      return window.getComputedStyle(root).position === "fixed";
    }

    function pin() {
      if (!isFixedLayout()) {
        root.style.boxSizing = "";
        root.style.top = "";
        root.style.right = "";
        root.style.bottom = "";
        root.style.left = "";
        root.style.width = "";
        root.style.height = "";
        return;
      }
      root.style.boxSizing = "border-box";
      root.style.top = vv.offsetTop + "px";
      root.style.left = vv.offsetLeft + "px";
      root.style.width = vv.width + "px";
      root.style.height = vv.height + "px";
      root.style.right = "auto";
      root.style.bottom = "auto";
    }

    vv.addEventListener("resize", function () {
      pin();
      /* Keyboard opened while replying — keep the latest message in view. */
      if (textarea && document.activeElement === textarea) {
        scrollThread(thread);
      }
    });
    vv.addEventListener("scroll", pin);
    pin();
  }

  function buildRow(msg) {
    var article = document.createElement("article");
    article.className =
      "hoocon-messenger__row hoocon-messenger__row--" + (msg.direction || "inbound");
    article.setAttribute("data-message-id", String(msg.id));

    var wrap = document.createElement("div");
    wrap.className = "hoocon-messenger__bubble-wrap";

    var sender = document.createElement("span");
    sender.className = "hoocon-messenger__sender";
    sender.textContent = msg.sender_name || "";

    var bubble = document.createElement("div");
    bubble.className = "hoocon-messenger__bubble";
    if (msg.body) {
      var text = document.createElement("span");
      text.className = "hoocon-messenger__bubble-text";
      text.textContent = msg.body;
      bubble.appendChild(text);
    }

    if (msg.attachment_url) {
      var link = document.createElement("a");
      link.className = "hoocon-messenger__attach";
      link.href = msg.attachment_url;
      link.target = "_blank";
      link.rel = "noopener";
      if (msg.attachment_is_image) {
        var img = document.createElement("img");
        img.className = "hoocon-messenger__attach-img";
        img.src = msg.attachment_url;
        img.alt = msg.attachment_name || "вложение";
        img.loading = "lazy";
        link.appendChild(img);
      } else {
        link.textContent = "📎 " + (msg.attachment_name || "файл");
      }
      bubble.appendChild(document.createTextNode(" "));
      bubble.appendChild(link);
    }

    var time = document.createElement("time");
    time.className = "hoocon-messenger__time";
    if (msg.created_at_iso) time.setAttribute("datetime", msg.created_at_iso);
    var label = msg.created_at_label || "";
    if (msg.outside_hours) label += " · вне часов";
    time.textContent = label;

    wrap.appendChild(sender);
    wrap.appendChild(bubble);
    wrap.appendChild(time);
    article.appendChild(wrap);
    return article;
  }

  function startPoll(root, thread) {
    var pollUrl = root.getAttribute("data-poll-url");
    if (!pollUrl) return;

    var afterId = Number(root.getAttribute("data-after-id") || "0") || 0;
    var pollMs = Number(root.getAttribute("data-poll-ms") || "3000") || 3000;
    var busy = false;

    async function tick() {
      if (busy || document.hidden) return;
      busy = true;
      try {
        var url = pollUrl + (pollUrl.indexOf("?") >= 0 ? "&" : "?") + "after=" + afterId;
        var resp = await fetch(url, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          cache: "no-store",
        });
        if (!resp.ok) return;
        var data = await resp.json();
        var list = (data && data.messages) || [];
        if (!list.length) return;

        var empty = document.getElementById("hoocon-messenger-empty");
        if (empty) empty.remove();

        var nearBottom =
          thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
        for (var i = 0; i < list.length; i += 1) {
          var msg = list[i];
          if (!msg || !msg.id) continue;
          if (thread.querySelector('[data-message-id="' + msg.id + '"]')) {
            afterId = Math.max(afterId, Number(msg.id) || 0);
            continue;
          }
          thread.appendChild(buildRow(msg));
          afterId = Math.max(afterId, Number(msg.id) || 0);
        }
        root.setAttribute("data-after-id", String(afterId));
        if (nearBottom) scrollThread(thread);
      } catch (err) {
        /* transient network — next tick retries */
      } finally {
        busy = false;
      }
    }

    void tick();
    window.setInterval(function () {
      void tick();
    }, pollMs);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) void tick();
    });
  }

  /**
   * Phone thread is a full-screen sheet — the Django change form (client,
   * status, assignee…) sits behind it. The ⓘ header button toggles
   * ``body.hoocon-chat-info-open``; CSS then lifts the form into a fixed
   * overlay with a floating close chip.
   */
  function setupInfoSheet() {
    var infoBtn = document.getElementById("hoocon-messenger-info");
    if (!infoBtn) return;

    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "hoocon-chat-info-close";
    closeBtn.textContent = "Закрыть";
    closeBtn.setAttribute("aria-label", "Закрыть карточку диалога");
    document.body.appendChild(closeBtn);

    function setOpen(open) {
      document.body.classList.toggle("hoocon-chat-info-open", open);
      if (open) {
        var formEl = document.querySelector("#content-main > form");
        if (formEl) formEl.scrollTop = 0;
        closeBtn.focus();
      } else {
        infoBtn.focus();
      }
    }

    infoBtn.addEventListener("click", function () {
      setOpen(true);
    });
    closeBtn.addEventListener("click", function () {
      setOpen(false);
    });
    document.addEventListener("keydown", function (event) {
      if (
        event.key === "Escape" &&
        document.body.classList.contains("hoocon-chat-info-open")
      ) {
        setOpen(false);
      }
    });
  }

  ready(function () {
    var root = document.getElementById("hoocon-messenger");
    var thread = document.getElementById("hoocon-messenger-thread");
    if (thread) scrollThread(thread);
    if (root && thread) startPoll(root, thread);
    setupInfoSheet();

    var form = document.getElementById("hoocon-messenger-reply");
    var textarea = document.getElementById("hoocon-reply-body");
    setupViewportPin(root, thread, textarea);

    var tplSelect = document.getElementById("hoocon-reply-template");
    if (tplSelect && textarea) {
      tplSelect.addEventListener("change", function () {
        var opt = tplSelect.options[tplSelect.selectedIndex];
        var body = opt ? opt.getAttribute("data-body") : "";
        if (body) {
          textarea.value = body;
          textarea.focus();
        }
        tplSelect.value = "";
      });
    }
    if (!form || !textarea) return;

    textarea.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" || event.shiftKey) return;
      if (event.isComposing || event.keyCode === 229) return;
      event.preventDefault();
      if (!textarea.value.trim()) return;
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.submit();
      }
    });

    form.addEventListener("submit", function () {
      var buttons = form.querySelectorAll('button[type="submit"]');
      for (var i = 0; i < buttons.length; i += 1) {
        buttons[i].disabled = true;
      }
    });
  });
})();
