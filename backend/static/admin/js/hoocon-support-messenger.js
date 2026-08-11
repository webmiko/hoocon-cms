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
    bubble.textContent = msg.body || "";

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

  ready(function () {
    var root = document.getElementById("hoocon-messenger");
    var thread = document.getElementById("hoocon-messenger-thread");
    if (thread) scrollThread(thread);
    if (root && thread) startPoll(root, thread);

    var form = document.getElementById("hoocon-messenger-reply");
    var textarea = document.getElementById("hoocon-reply-body");
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
      var btn = form.querySelector(".hoocon-messenger__send");
      if (btn) btn.disabled = true;
    });
  });
})();
