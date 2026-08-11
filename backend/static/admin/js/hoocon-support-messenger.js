/**
 * Support conversation messenger (Admin change form).
 * Enter sends; Shift+Enter inserts a newline. Scrolls thread to latest.
 */
(function () {
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  ready(function () {
    var thread = document.getElementById("hoocon-messenger-thread");
    if (thread) {
      thread.scrollTop = thread.scrollHeight;
    }

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
