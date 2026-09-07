/**
 * Reverse proxy: VPS → this Worker → api.telegram.org
 * Path shape matches Bot API: /bot<token>/<method>
 * Optional ALLOWED_IPS env (comma-separated) to restrict callers.
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return Response.json({ ok: true, service: "hoocon-telegram-api" });
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
