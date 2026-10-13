/**
 * Док телефона на страницах админки.
 *
 * Сам звонок живёт в окне «Телефон» (/admin/crm/softphone/, hoocon-softphone-window.js):
 * страницы админки перезагружаются, и звонок внутри страницы оборвался бы.
 * Док показывает состояние окна (на линии / входящий / идёт разговор), даёт
 * «Ответить» и «Завершить» и превращает кнопку «Позвонить клиенту» и ссылки
 * tel: в набор через это окно. Ctrl/⌘/Shift-клик оставляет прежнее поведение.
 *
 * Скрипт отдаётся только сотрудникам с токеном WebRTC
 * (config.unfold_callbacks.admin_softphone_js); остальным — пустой файл.
 */
(function () {
  "use strict";

  if (window.__hooconSoftphoneDock || !("BroadcastChannel" in window)) {
    return;
  }
  window.__hooconSoftphoneDock = true;

  const WINDOW_URL = "/admin/crm/softphone/";
  const WINDOW_NAME = "hoocon-softphone";
  const WINDOW_FEATURES = "popup=yes,width=380,height=640,resizable=yes";
  const PROBE_MS = 5000;
  const STALE_MS = 11000;
  const FIRST_REPLY_MS = 1500;
  const PROBE_WAIT_MS = 400;
  const CALL_CLIENT_RE = /^\/admin\/crm\/client\/\d+\/call-client\/$/;

  const channel = new BroadcastChannel("hoocon-softphone");
  let popupState = null;
  let lastSeen = 0;
  let pendingDial = "";
  const root = document.createElement("div");

  // Ссылки «Открыть карточку» в окне телефона нацелены на эту вкладку.
  if (!window.name) {
    window.name = "hoocon-admin";
  }

  const script = document.currentScript;
  if (script && script.src) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = script.src.replace("/js/hoocon-softphone-dock.js", "/css/hoocon-softphone.css");
    document.head.appendChild(link);
  }

  function button(className, text, action) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = className;
    el.textContent = text;
    if (action) {
      el.dataset.act = action;
    }
    return el;
  }

  root.className = "hsp-dock";
  root.setAttribute("role", "region");
  root.setAttribute("aria-label", "Телефон");
  root.dataset.state = "closed";

  const main = button("hsp-dock__main", "", "open");
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "call";
  const dot = document.createElement("span");
  dot.className = "hsp-dock__dot";
  dot.setAttribute("aria-hidden", "true");
  const label = document.createElement("span");
  label.className = "hsp-dock__label";
  const timer = document.createElement("span");
  timer.className = "hsp-dock__timer";
  main.append(icon, dot, label, timer);

  const answer = button("hsp-dock__act hsp-dock__act--ok", "Ответить", "answer");
  const hangup = button("hsp-dock__act hsp-dock__act--bad", "Завершить", "hangup");
  const live = document.createElement("span");
  live.className = "hsp-dock__live";
  live.setAttribute("aria-live", "assertive");
  root.append(main, answer, hangup, live);

  function isAlive() {
    return lastSeen > 0 && Date.now() - lastSeen < STALE_MS;
  }

  function formatTimer(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    return String(Math.floor(total / 60)).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0");
  }

  function callTitle(call) {
    return call.name || call.phone || "Неизвестный номер";
  }

  let announced = "";
  function render() {
    let state = "closed";
    let text = "Телефон";
    let title = "Открыть окно телефона";
    let call = null;
    if (isAlive() && popupState) {
      call = popupState.call;
      if (call && call.direction === "incoming" && call.state !== "confirmed") {
        state = "ringing";
        text = "Входящий: " + callTitle(call);
        title = "Открыть окно телефона";
      } else if (call) {
        state = "talking";
        text = callTitle(call);
        title = "Открыть окно телефона";
      } else if (!popupState.started) {
        state = "off";
        text = "Включить телефон";
        title = "В окне телефона нажмите «Включить телефон»";
      } else if (popupState.phase === "error") {
        state = "error";
        text = "Ошибка телефона";
        title = popupState.error || "Откройте окно телефона";
      } else if (popupState.phase === "ready") {
        state = "ready";
        text = "На линии";
      } else {
        state = "connecting";
        text = "Подключение…";
      }
    }
    root.dataset.state = state;
    label.textContent = text;
    main.title = title;
    main.setAttribute("aria-label", text + ". " + title);
    answer.hidden = state !== "ringing";
    hangup.hidden = !(state === "ringing" || state === "talking");
    hangup.textContent = state === "ringing" ? "Отклонить" : "Завершить";
    if (state === "talking" && call && call.state === "confirmed" && call.startedAt) {
      timer.textContent = formatTimer(Date.now() - call.startedAt);
    } else {
      timer.textContent = "";
    }
    // Скринридер читает входящий один раз на звонок.
    const note = state === "ringing" ? text : "";
    if (note !== announced) {
      announced = note;
      live.textContent = note;
    }
  }

  function focusWindow() {
    // window.open(url, name) на живом окне перезагрузил бы его и сбросил линию:
    // к живому обращаемся без адреса, адрес даём только вновь созданному.
    const popup = window.open("", WINDOW_NAME);
    if (!popup) {
      return null;
    }
    if (popup.location.href === "about:blank") {
      popup.location.replace(WINDOW_URL);
    }
    popup.focus();
    return popup;
  }

  function withAlive(callback) {
    // Свежее состояние — действуем сразу (всплывающее окно требует свежего клика).
    // Иначе окно могло быть живо, но фоново: коротко спрашиваем и решаем.
    if (isAlive()) {
      callback(true);
      return;
    }
    const before = lastSeen;
    channel.postMessage({ type: "hello" });
    window.setTimeout(function () {
      callback(lastSeen > before);
    }, PROBE_WAIT_MS);
  }

  function openWindow() {
    withAlive(function (alive) {
      if (alive) {
        focusWindow();
      } else {
        window.open(WINDOW_URL, WINDOW_NAME, WINDOW_FEATURES);
      }
    });
  }

  function dialNumber(number) {
    pendingDial = number;
    withAlive(function (alive) {
      if (alive) {
        channel.postMessage({ type: "dial", phone: number });
        pendingDial = "";
        focusWindow();
      } else {
        // Номер уйдёт, когда окно загрузится и первым делом пришлёт состояние.
        const popup = window.open(WINDOW_URL, WINDOW_NAME, WINDOW_FEATURES);
        if (!popup) {
          pendingDial = "";
          window.alert("Браузер заблокировал окно телефона. Разрешите всплывающие окна для этого сайта.");
        }
      }
    });
  }

  channel.onmessage = function (event) {
    const message = event.data || {};
    if (message.type === "state") {
      popupState = message.state || null;
      lastSeen = Date.now();
      if (pendingDial) {
        channel.postMessage({ type: "dial", phone: pendingDial });
        pendingDial = "";
      }
    } else if (message.type === "closed") {
      popupState = null;
      lastSeen = 0;
    }
    render();
  };

  root.addEventListener("click", function (event) {
    const target = event.target.closest("[data-act]");
    if (!target) {
      return;
    }
    if (target.dataset.act === "open") {
      openWindow();
    } else if (target.dataset.act === "answer") {
      channel.postMessage({ type: "answer" });
    } else if (target.dataset.act === "hangup") {
      channel.postMessage({ type: "hangup" });
    }
  });

  document.addEventListener(
    "click",
    function (event) {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      const link = event.target.closest ? event.target.closest("a[href]") : null;
      if (!link) {
        return;
      }
      let number = "";
      if (link.protocol === "tel:") {
        try {
          number = decodeURIComponent(link.getAttribute("href").slice(4));
        } catch (err) {
          return;
        }
      } else if (CALL_CLIENT_RE.test(link.pathname)) {
        const field = document.getElementById("id_phone");
        number = field ? field.value.trim() : "";
      }
      // Без номера на странице остаётся прежняя страница «Позвонить клиенту».
      if (!number) {
        return;
      }
      event.preventDefault();
      dialNumber(number);
    },
    true,
  );

  function init() {
    document.body.appendChild(root);
    render();
    channel.postMessage({ type: "hello" });
    window.setTimeout(render, FIRST_REPLY_MS);
    window.setInterval(function () {
      channel.postMessage({ type: "hello" });
      render();
    }, PROBE_MS);
    window.setInterval(render, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
