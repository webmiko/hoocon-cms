/**
 * Admin WebAuthn passkeys — login + registration helpers (CSP-safe, no inline).
 *
 * Expects data attributes on #hoocon-passkey-root:
 *   data-login-begin / data-login-complete  (login page)
 *   data-register-begin / data-register-complete (manage page)
 *   data-next (optional redirect after login)
 */
(function () {
  "use strict";

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function csrfHeaders() {
    return {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
      "X-Requested-With": "XMLHttpRequest",
    };
  }

  function setStatus(el, text, isError) {
    if (!el) return;
    el.textContent = text || "";
    el.hidden = !text;
    el.classList.toggle("text-red-600", !!isError);
    el.classList.toggle("dark:text-red-400", !!isError);
  }

  function bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let str = "";
    for (let i = 0; i < bytes.length; i += 1) {
      str += String.fromCharCode(bytes[i]);
    }
    return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  function base64urlToBuffer(value) {
    const pad = "=".repeat((4 - (value.length % 4)) % 4);
    const b64 = (value + pad).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(b64);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) {
      out[i] = raw.charCodeAt(i);
    }
    return out.buffer;
  }

  function parseCreationOptions(publicKey) {
    if (
      window.PublicKeyCredential &&
      typeof PublicKeyCredential.parseCreationOptionsFromJSON === "function"
    ) {
      return PublicKeyCredential.parseCreationOptionsFromJSON(publicKey);
    }
    const opts = structuredClone(publicKey);
    opts.challenge = base64urlToBuffer(opts.challenge);
    opts.user.id = base64urlToBuffer(opts.user.id);
    if (Array.isArray(opts.excludeCredentials)) {
      opts.excludeCredentials = opts.excludeCredentials.map(function (c) {
        return Object.assign({}, c, { id: base64urlToBuffer(c.id) });
      });
    }
    return opts;
  }

  function parseRequestOptions(publicKey) {
    if (
      window.PublicKeyCredential &&
      typeof PublicKeyCredential.parseRequestOptionsFromJSON === "function"
    ) {
      return PublicKeyCredential.parseRequestOptionsFromJSON(publicKey);
    }
    const opts = structuredClone(publicKey);
    opts.challenge = base64urlToBuffer(opts.challenge);
    if (Array.isArray(opts.allowCredentials)) {
      opts.allowCredentials = opts.allowCredentials.map(function (c) {
        return Object.assign({}, c, { id: base64urlToBuffer(c.id) });
      });
    }
    return opts;
  }

  function credentialToJSON(cred) {
    if (typeof cred.toJSON === "function") {
      return cred.toJSON();
    }
    const response = cred.response;
    const out = {
      id: cred.id,
      rawId: bufferToBase64url(cred.rawId),
      type: cred.type,
      clientExtensionResults:
        typeof cred.getClientExtensionResults === "function"
          ? cred.getClientExtensionResults()
          : {},
      response: {
        clientDataJSON: bufferToBase64url(response.clientDataJSON),
      },
    };
    if (response.attestationObject) {
      out.response.attestationObject = bufferToBase64url(response.attestationObject);
    }
    if (response.authenticatorData) {
      out.response.authenticatorData = bufferToBase64url(response.authenticatorData);
    }
    if (response.signature) {
      out.response.signature = bufferToBase64url(response.signature);
    }
    if (response.userHandle) {
      out.response.userHandle = bufferToBase64url(response.userHandle);
    }
    if (cred.authenticatorAttachment) {
      out.authenticatorAttachment = cred.authenticatorAttachment;
    }
    return out;
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: csrfHeaders(),
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try {
      data = await res.json();
    } catch (_err) {
      data = {};
    }
    if (!res.ok || data.ok === false) {
      const msg = (data && data.error) || "Ошибка запроса (" + res.status + ")";
      throw new Error(msg);
    }
    return data;
  }

  async function loginWithPasskey(root) {
    const status = root.querySelector("[data-passkey-status]");
    const beginUrl = root.dataset.loginBegin;
    const completeUrl = root.dataset.loginComplete;
    const next = root.dataset.next || "/admin/";
    if (!beginUrl || !completeUrl) return;

    if (!window.PublicKeyCredential) {
      setStatus(status, "Браузер не поддерживает ключи доступа (WebAuthn).", true);
      return;
    }

    setStatus(status, "Ожидаем ключ (Связка ключей / Google)…", false);
    try {
      const begin = await postJSON(beginUrl, { next: next });
      const publicKey = parseRequestOptions(begin.publicKey);
      const assertion = await navigator.credentials.get({ publicKey: publicKey });
      if (!assertion) {
        throw new Error("Вход отменён.");
      }
      const done = await postJSON(completeUrl, {
        credential: credentialToJSON(assertion),
      });
      window.location.href = done.redirect || next;
    } catch (err) {
      const name = err && err.name;
      if (name === "NotAllowedError") {
        setStatus(status, "Вход по ключу отменён.", true);
      } else {
        setStatus(status, (err && err.message) || "Не удалось войти по ключу.", true);
      }
    }
  }

  async function registerPasskey(root) {
    const status = root.querySelector("[data-passkey-status]");
    const beginUrl = root.dataset.registerBegin;
    const completeUrl = root.dataset.registerComplete;
    const nameInput = root.querySelector("[data-passkey-name]");
    if (!beginUrl || !completeUrl) return;

    if (!window.PublicKeyCredential) {
      setStatus(status, "Браузер не поддерживает ключи доступа (WebAuthn).", true);
      return;
    }

    setStatus(status, "Создаём ключ — подтвердите в системе…", false);
    try {
      const begin = await postJSON(beginUrl, {});
      const publicKey = parseCreationOptions(begin.publicKey);
      const cred = await navigator.credentials.create({ publicKey: publicKey });
      if (!cred) {
        throw new Error("Регистрация отменена.");
      }
      const deviceName = nameInput ? String(nameInput.value || "").trim() : "";
      await postJSON(completeUrl, {
        credential: credentialToJSON(cred),
        device_name: deviceName,
      });
      window.location.reload();
    } catch (err) {
      const name = err && err.name;
      if (name === "NotAllowedError") {
        setStatus(status, "Регистрация ключа отменена.", true);
      } else if (name === "InvalidStateError") {
        setStatus(status, "Этот ключ уже добавлен на устройстве.", true);
      } else {
        setStatus(status, (err && err.message) || "Не удалось добавить ключ.", true);
      }
    }
  }

  function init() {
    const root = document.getElementById("hoocon-passkey-root");
    if (!root) return;

    const loginBtn = root.querySelector("[data-passkey-login]");
    if (loginBtn) {
      loginBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        loginWithPasskey(root);
      });
    }

    const registerBtn = root.querySelector("[data-passkey-register]");
    if (registerBtn) {
      registerBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        registerPasskey(root);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
