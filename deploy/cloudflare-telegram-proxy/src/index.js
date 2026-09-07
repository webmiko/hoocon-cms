/**
 * 1) Outbound: VPS → Worker → api.telegram.org  (/bot… /file/bot…)
 * 2) Inbound:  Telegram → Worker /webhook → hoocon.ru webhook
 *
 * Env:
 *   ALLOWED_IPS — optional comma IPs for outbound Bot API paths only
 *   WEBHOOK_FORWARD_URL — Django webhook URL (required for /webhook)
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return Response.json({ ok: true, service: "hoocon-telegram-api" });
    }

    if (url.pathname === "/webhook") {
      return forwardInboundWebhook(request, env);
    }

    const allowed = String(env.ALLOWED_IPS || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (allowed.length) {
      const ip = request.headers.get("CF-Connecting-IP") || "";
      if (!allowed.includes(ip)) {
        return new Response("Forbidden", { status: 403 });
      }
    }

    // Only Bot API paths: /botTOKEN/... or /file/botTOKEN/...
    if (!/^\/(bot|file\/bot)/.test(url.pathname)) {
      return new Response("Not Found", { status: 404 });
    }

    const target = new URL(url.pathname + url.search, "https://api.telegram.org");
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("cf-connecting-ip");
    headers.delete("cf-ray");
    headers.delete("cf-visitor");
    headers.delete("cf-ipcountry");
    headers.delete("x-forwarded-proto");
    headers.delete("x-real-ip");

    const init = {
      method: request.method,
      headers,
      redirect: "follow",
    };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
      init.duplex = "half";
    }

    try {
      const upstream = await fetch(target.toString(), init);
      return new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers: upstream.headers,
      });
    } catch (err) {
      return Response.json(
        { ok: false, error: "upstream_failed", detail: String(err && err.message) },
        { status: 502 },
      );
    }
  },
};

async function forwardInboundWebhook(request, env) {
  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }
  const target = String(env.WEBHOOK_FORWARD_URL || "").trim();
  if (!target) {
    return Response.json({ ok: false, error: "WEBHOOK_FORWARD_URL unset" }, { status: 500 });
  }

  const headers = new Headers();
  headers.set("Content-Type", request.headers.get("Content-Type") || "application/json");
  const secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
  if (secret) {
    headers.set("X-Telegram-Bot-Api-Secret-Token", secret);
  }
  headers.set("User-Agent", "HooconTelegramProxy/1.12");

  try {
    const upstream = await fetch(target, {
      method: "POST",
      headers,
      body: request.body,
      duplex: "half",
      redirect: "follow",
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") || "application/json" },
    });
  } catch (err) {
    return Response.json(
      { ok: false, error: "forward_failed", detail: String(err && err.message) },
      { status: 502 },
    );
  }
}
