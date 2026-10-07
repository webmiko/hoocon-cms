/**
 * Chained autocomplete: «Заявка» / «КП» / «Заказ» show only rows of the
 * selected «Клиент».
 *
 * Django's admin/js/autocomplete.js sends fixed params (term/app/model/
 * field). This patch wraps the Select2 ajax data function of each chained
 * field, adding `client=<id>`; the target model's admin filters its
 * queryset server-side (config.admin_mixins.filter_autocomplete_by_client).
 *
 * Client change clears a stale chained selection — it almost surely
 * belongs to another client.
 */
(function () {
  "use strict";

  /** Parent field id → chained autocomplete field ids on the same form. */
  var CHAIN = {
    id_client: ["id_lead", "id_quote", "id_order"],
  };

  function init() {
    var jq = window.django && window.django.jQuery;
    if (!jq) {
      return;
    }

    Object.keys(CHAIN).forEach(function (parentId) {
      var parent = document.getElementById(parentId);
      if (!parent) {
        return;
      }
      CHAIN[parentId].forEach(function (childId) {
        chainField(parent, document.getElementById(childId), jq);
      });
      jq(parent).on("change", function () {
        CHAIN[parentId].forEach(function (childId) {
          var child = document.getElementById(childId);
          if (child) {
            jq(child).val(null).trigger("change");
          }
        });
      });
    });
  }

  /** Extend the child's Select2 ajax params with the parent's value. */
  function chainField(parent, child, jq) {
    if (!child) {
      return;
    }
    var attempts = 0;
    var timer = window.setInterval(function () {
      attempts += 1;
      var instance = jq(child).data("select2");
      /*
       * AjaxAdapter copies the ajax config at init
       * (_applyDefaults → $.extend({}, defaults, options)) — mutating
       * options.options.ajax later does nothing. The live config is
       * dataAdapter.ajaxOptions; patch the merged copy too as fallback.
       */
      var live =
        instance && instance.dataAdapter && instance.dataAdapter.ajaxOptions;
      var merged =
        instance &&
        instance.options &&
        instance.options.options &&
        instance.options.options.ajax;
      if (live || merged || attempts >= 40) {
        window.clearInterval(timer);
      }
      if (!live && !merged) {
        return;
      }
      var dataFn = function (params) {
        return {
          term: params.term,
          page: params.page,
          app_label: child.dataset.appLabel,
          model_name: child.dataset.modelName,
          field_name: child.dataset.fieldName,
          client: parent.value || "",
        };
      };
      if (live) {
        live.data = dataFn;
      }
      if (merged) {
        merged.data = dataFn;
      }
    }, 50);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
