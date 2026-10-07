/**
 * Client change form: inline action buttons next to contact fields.
 *
 * «Написать» рядом с email → compose-email, «Позвонить» рядом с phone →
 * call-client. Object id берётся из URL /admin/crm/client/<pk>/change/.
 */
(function () {
  "use strict";

  var match = window.location.pathname.match(/\/admin\/crm\/client\/(\d+)\/change\//);
  if (!match) {
    return;
  }
  var clientId = match[1];

  function addAction(inputId, url, icon, label) {
    var input = document.getElementById(inputId);
    if (!input || input.closest(".hoocon-field-action")) {
      return;
    }
    var row = document.createElement("div");
    row.className = "hoocon-field-action";
    input.parentNode.insertBefore(row, input);
    row.appendChild(input);

    var link = document.createElement("a");
    link.href = url;
    link.className = "hoocon-field-action__btn";
    link.title = label;
    link.setAttribute("aria-label", label);
    var iconEl = document.createElement("span");
    iconEl.className = "material-symbols-outlined";
    iconEl.setAttribute("aria-hidden", "true");
    iconEl.textContent = icon;
    link.appendChild(iconEl);
    row.appendChild(link);
  }

  function init() {
    addAction(
      "id_email",
      "/admin/crm/client/" + clientId + "/compose-email/",
      "mail",
      "Написать письмо",
    );
    addAction(
      "id_phone",
      "/admin/crm/client/" + clientId + "/call-client/",
      "call",
      "Позвонить клиенту",
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
