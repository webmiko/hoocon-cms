/**
 * Окно «Телефон»: UIS WebRTC живёт здесь и не обрывается переходами по админке.
 *
 * Библиотека: vendor/uis_webrtc-2.0.2.min.js (npm @uiscom/uis_webrtc, ISC).
 * Остальные страницы админки (hoocon-softphone-dock.js) говорят с окном через
 * BroadcastChannel «hoocon-softphone»: dial / answer / hangup / hello — туда,
 * state / closed — обратно. Канал ограничен одним origin.
 *
 * Токен WebRTC берётся POST-ом у сервера (только свой, см. crm/softphone.py)
 * и держится в памяти окна; в DOM и localStorage не пишется.
 */
(function () {
  "use strict";

  const root = document.getElementById("hsp");
  if (!root || root.dataset.blocked === "1") {
    return;
  }

  const CHANNEL = "hoocon-softphone";
  const ERRORS = {
    microphoneAccessDenied:
      "Нет доступа к микрофону. Разрешите его (значок замка у адреса) и нажмите «Включить телефон».",
    invalidToken:
      "Токен WebRTC не подошёл. Попросите администратора выпустить новый и сохранить в вашем профиле.",
    authorzationFailed:
      "Токен WebRTC не подошёл. Попросите администратора выпустить новый и сохранить в вашем профиле.",
    registrationFailed:
      "Не удалось подключить SIP-линию. Проверьте, что у вас есть SIP-линия в кабинете UIS.",
    telephonyIsUnavailable:
      "Телефония UIS сейчас недоступна. Попробуйте нажать «Включить телефон» чуть позже.",
    appAlreadyOpened:
      "Телефон уже открыт в другом окне или в программе UIS. Закройте софтфон UIS и нажмите «Включить телефон».",
    unknownError: "Ошибка телефона. Нажмите «Включить телефон» ещё раз.",
  };

  const els = {};
  root.querySelectorAll("[data-role]").forEach(function (el) {
    els[el.dataset.role] = el;
  });
  const channel = "BroadcastChannel" in window ? new BroadcastChannel(CHANNEL) : null;

  let phone = null;
  let started = false;
  let pendingDial = "";
  let snapshot = {};
  let call = null; // {direction, state, phone, name, company, url, holded, muted, startedAt}
  let lookupKey = "";
  let phase = "off"; // off | connecting | ready | error
  let errorText = "";
  let employee = "";

  function digitsFor(raw) {
    // Same rule as crm.telephony.normalize_phone_digits: 8… → 7…, 10 digits → 7…
    let digits = String(raw || "").replace(/\D+/g, "");
    if (digits.length === 11 && digits.charAt(0) === "8") {
      digits = "7" + digits.slice(1);
    } else if (digits.length === 10) {
      digits = "7" + digits;
    }
    return digits;
  }

  function validNumber(raw) {
    const digits = digitsFor(raw);
    return digits.length >= 3 && digits.length <= 15;
  }

  function show(el, visible) {
    if (el) {
      el.hidden = !visible;
    }
  }

  function formatTimer(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const mm = String(Math.floor(total / 60)).padStart(2, "0");
    const ss = String(total % 60).padStart(2, "0");
    return mm + ":" + ss;
  }

  function post(message) {
    if (channel) {
      channel.postMessage(message);
    }
  }

  function publicState() {
    return {
      started: started,
      phase: phase,
      error: errorText,
      employee: employee,
      call: call
        ? {
            direction: call.direction,
            state: call.state,
            phone: call.phone,
            name: call.name || "",
            company: call.company || "",
            url: call.url || "",
            holded: !!call.holded,
            muted: !!call.muted,
            startedAt: call.startedAt || 0,
          }
        : null,
    };
  }

  function render() {
    const statusText = {
      off: "Телефон выключен",
      connecting: "Подключение…",
      ready: "На линии",
      error: "Ошибка",
    }[phase];
    els.status.textContent = statusText;
    els.employee.textContent = employee;
    root.dataset.phase = phase;

    show(els.start, !started);
    show(els.dialer, started && phase === "ready" && !call);
    show(els.keys, started && phase === "ready");
    show(els.call, !!call);

    if (errorText) {
      els.error.textContent = errorText;
    }
    show(els.error, !!errorText);

    if (call) {
      const incoming = call.direction === "incoming";
      const talking = call.state === "confirmed";
      let label = incoming ? "Входящий звонок" : "Исходящий";
      if (talking) {
        label = "Разговор";
      } else if (!incoming) {
        label = call.state === "sending" ? "Вызов…" : "Идёт дозвон…";
      }
      els.direction.textContent = label;
      els.who.textContent = call.name || call.phone || "Неизвестный номер";
      els.number.textContent = call.name ? call.phone : "";
      show(els.number, !!call.name);
      if (call.url) {
        els.card.href = call.url;
        show(els.card, true);
      } else {
        show(els.card, false);
      }
      show(els.answer, incoming && !talking);
      show(els.hold, talking);
      show(els.mute, talking);
      els.hold.textContent = call.holded ? "Вернуть в разговор" : "Удержать";
      els.mute.textContent = call.muted ? "Включить микрофон" : "Выключить микрофон";
      els.hangup.textContent = incoming && !talking ? "Отклонить" : "Завершить";
      tickTimer();
      document.title = (incoming && !talking ? "Входящий: " : "Звонок: ") + (call.name || call.phone || "");
    } else {
      document.title = "Телефон · Hoocon";
    }
    post({ type: "state", state: publicState() });
  }

  function tickTimer() {
    if (call && call.state === "confirmed" && call.startedAt) {
      els.timer.textContent = formatTimer(Date.now() - call.startedAt);
      show(els.timer, true);
    } else {
      show(els.timer, false);
    }
  }

  function fail(text) {
    errorText = text;
    render();
  }

  function guarded(action) {
    try {
      action();
      errorText = "";
    } catch (err) {
      errorText = err && err.message ? err.message : "Действие не выполнено.";
    }
    render();
  }

  function lookupCaller(key, number) {
    if (lookupKey === key) {
      return;
    }
    lookupKey = key;
    fetch(root.dataset.lookupUrl + "?phone=" + encodeURIComponent(number), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        return response.ok ? response.json() : { found: false };
      })
      .then(function (data) {
        if (lookupKey !== key || !call || !data.found) {
          return;
        }
        call.name = data.name || "";
        call.company = data.company || "";
        call.url = data.url || "";
        render();
      })
      .catch(function () {
        /* Имя клиента — удобство; без него звонок работает. */
      });
  }

  // Ошибка библиотеки (микрофон, токен, другой софтфон) — телефон гасим и возвращаем кнопку
  // «Включить телефон»: после исправления причины менеджеру не нужно перезагружать окно.
  function stopAfterError(code) {
    const dead = phone;
    phone = null;
    started = false;
    call = null;
    lookupKey = "";
    phase = "error";
    errorText = ERRORS[code] || ERRORS.unknownError;
    if (dead) {
      try {
        dead.destroy();
      } catch (err) {
        /* уже выключен */
      }
    }
    render();
  }

  function onState(st) {
    if (!st || typeof st !== "object") {
      return;
    }
    if (st.error) {
      stopAfterError(st.error);
      return;
    }
    snapshot = st;
    employee = (st.employee && st.employee.name) || employee;
    if (st.available) {
      phase = "ready";
      if (errorText && !call) {
        errorText = "";
      }
    } else {
      phase = st.destroyed ? "off" : "connecting";
    }

    const live = st.state === "sending" || st.state === "progress" || st.state === "confirmed";
    if (live && st.phoneNumber) {
      const key = st.direction + ":" + st.phoneNumber;
      const previous = call;
      const sameCall = previous && previous.direction === st.direction && previous.phone === st.phoneNumber;
      call = sameCall ? previous : { direction: st.direction, phone: st.phoneNumber, name: "", url: "" };
      if (!sameCall) {
        lookupKey = "";
        lookupCaller(key, st.phoneNumber);
      }
      if (st.state === "confirmed" && call.state !== "confirmed") {
        call.startedAt = Date.now();
      }
      call.state = st.state;
      call.holded = st.holded;
      call.muted = st.muted;
    } else {
      call = null;
      lookupKey = "";
    }
    render();
    if (phase === "ready" && pendingDial && !call) {
      const number = pendingDial;
      pendingDial = "";
      dial(number);
    }
  }

  function dial(raw) {
    if (!validNumber(raw)) {
      fail("Введите номер: от 3 до 15 цифр.");
      return;
    }
    if (!started) {
      pendingDial = raw;
      els.number_input.value = raw;
      fail("Нажмите «Включить телефон» — потом набор продолжится сам.");
      return;
    }
    if (call) {
      fail("Уже идёт разговор. Завершите его, прежде чем набирать другой номер.");
      return;
    }
    if (phase !== "ready" || !phone) {
      pendingDial = raw;
      return;
    }
    guarded(function () {
      phone.call(digitsFor(raw));
    });
  }

  function start() {
    if (started) {
      return;
    }
    started = true;
    errorText = "";
    phase = "connecting";
    render();
    fetch(root.dataset.sessionUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": root.dataset.csrf, Accept: "application/json" },
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.body.token) {
          throw new Error(result.body.detail || "Не удалось получить токен телефона.");
        }
        employee = result.body.name || "";
        const Lib = window.uis_webrtc || window.UISWebRTC;
        if (!Lib || typeof Lib.create !== "function") {
          throw new Error("Библиотека телефона не загрузилась. Обновите окно.");
        }
        const instance = Lib.create({ token: result.body.token, shouldPlayCallEndingSignal: true });
        phone = instance;
        // События погашенного экземпляра (после ошибки) не должны трогать новый запуск.
        instance.onStateChange(function (st) {
          if (phone === instance) {
            onState(st);
          }
        });
        instance.on("error", function (code) {
          if (phone === instance) {
            stopAfterError(code);
          }
        });
      })
      .catch(function (err) {
        started = false;
        phase = "error";
        fail(err && err.message ? err.message : ERRORS.unknownError);
      });
  }

  root.addEventListener("click", function (event) {
    const target = event.target.closest("[data-action],[data-key]");
    if (!target) {
      return;
    }
    if (target.dataset.key) {
      if (call && call.state === "confirmed" && phone) {
        guarded(function () {
          phone.sendDTMF(target.dataset.key);
        });
      } else {
        els.number_input.value += target.dataset.key;
        els.number_input.focus();
      }
      return;
    }
    switch (target.dataset.action) {
      case "start":
        start();
        break;
      case "answer":
        guarded(function () {
          phone.answer();
        });
        break;
      case "hangup":
        guarded(function () {
          phone.terminate();
        });
        break;
      case "hold":
        guarded(function () {
          if (call && call.holded) {
            phone.unhold();
          } else {
            phone.hold();
          }
        });
        break;
      case "mute":
        guarded(function () {
          if (call && call.muted) {
            phone.unmute();
          } else {
            phone.mute();
          }
        });
        break;
      case "erase":
        els.number_input.value = els.number_input.value.slice(0, -1);
        break;
      default:
        break;
    }
  });

  els.dial_form.addEventListener("submit", function (event) {
    event.preventDefault();
    dial(els.number_input.value);
  });

  if (channel) {
    channel.onmessage = function (event) {
      const message = event.data || {};
      switch (message.type) {
        case "hello":
          post({ type: "state", state: publicState() });
          break;
        case "dial":
          dial(String(message.phone || ""));
          break;
        case "answer":
          if (phone && call && call.direction === "incoming") {
            guarded(function () {
              phone.answer();
            });
          }
          break;
        case "hangup":
          if (phone && call) {
            guarded(function () {
              phone.terminate();
            });
          }
          break;
        default:
          break;
      }
    };
  }

  // Свежесть окна проверяет док (hello → state): у фонового окна браузер режет таймеры,
  // а ответ на сообщение канала приходит сразу.
  window.setInterval(tickTimer, 1000);

  window.addEventListener("beforeunload", function (event) {
    if (call) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  window.addEventListener("pagehide", function () {
    post({ type: "closed" });
    if (phone) {
      try {
        phone.destroy();
      } catch (err) {
        /* уже выключен */
      }
    }
  });

  render();
})();
