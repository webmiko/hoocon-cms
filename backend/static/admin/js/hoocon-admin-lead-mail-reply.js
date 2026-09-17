/**
 * Lead reply: try installed Yandex Mail (app / Android intent), else web compose.
 */
(function () {
  "use strict";

  var FALLBACK_MS = 1200;

  function openWeb(webUrl) {
    if (!webUrl) {
      return;
    }
    window.open(webUrl, "_blank", "noopener,noreferrer");
  }

  function tryNativeThenWeb(nativeUrl, webUrl) {
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

    window.location.href = nativeUrl;
  }

  function openLeadReply(link) {
    var webUrl = link.dataset.webUrl || link.getAttribute("href") || "";
    var appUrl = link.dataset.yandexAppUrl || "";
    var androidUrl = link.dataset.yandexAndroidUrl || "";
    var ua = navigator.userAgent || "";

    if (/Android/i.test(ua) && androidUrl) {
      tryNativeThenWeb(androidUrl, webUrl);
      return;
    }
    if (/iPhone|iPad|iPod/i.test(ua) && appUrl) {
      tryNativeThenWeb(appUrl, webUrl);
      return;
    }
    if (appUrl) {
      tryNativeThenWeb(appUrl, webUrl);
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
