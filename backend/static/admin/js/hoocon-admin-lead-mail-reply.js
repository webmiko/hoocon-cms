/**
 * Lead reply: mailto / Android intent for Yandex Mail app, else web compose.
 * yandexmail:// does not pass compose fields; mailto is the supported path.
 */
(function () {
  "use strict";

  var FALLBACK_MS = 1500;

  function openWeb(webUrl) {
    if (!webUrl) {
      return;
    }
    window.open(webUrl, "_blank", "noopener,noreferrer");
  }

  function openMailto(mailtoUrl) {
    if (!mailtoUrl) {
      return;
    }
    var anchor = document.createElement("a");
    anchor.href = mailtoUrl;
    anchor.rel = "noopener noreferrer";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }

  function tryNativeThenWeb(nativeUrl, webUrl, useMailtoClick) {
    if (!nativeUrl) {
      openWeb(webUrl);
      return;
    }

    var fallbackTimer;
    var cleared = false;

    function clearFallback() {
      if (cleared) {
        return;
      }
      cleared = true;
      if (fallbackTimer) {
        window.clearTimeout(fallbackTimer);
      }
    }

    function onHide() {
      clearFallback();
    }

    document.addEventListener("visibilitychange", onHide, { once: true });
    window.addEventListener("pagehide", onHide, { once: true });
    window.addEventListener("blur", onHide, { once: true });

    fallbackTimer = window.setTimeout(function () {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onHide);
      window.removeEventListener("blur", onHide);
      if (!cleared) {
        cleared = true;
        openWeb(webUrl);
      }
    }, FALLBACK_MS);

    if (useMailtoClick) {
      openMailto(nativeUrl);
      return;
    }
    window.location.href = nativeUrl;
  }

  function openLeadReply(link) {
    var webUrl = link.dataset.webUrl || link.getAttribute("href") || "";
    var mailtoUrl = link.dataset.mailtoUrl || "";
    var androidUrl = link.dataset.yandexAndroidUrl || "";
    var ua = navigator.userAgent || "";

    if (/Android/i.test(ua) && androidUrl) {
      tryNativeThenWeb(androidUrl, webUrl, false);
      return;
    }
    if (mailtoUrl) {
      tryNativeThenWeb(mailtoUrl, webUrl, true);
      return;
    }
    openWeb(webUrl);
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest("a.hoocon-lead-yandex-mail-reply");
    if (!link) {
      return;
    }
    event.preventDefault();
    openLeadReply(link);
  });
})();
