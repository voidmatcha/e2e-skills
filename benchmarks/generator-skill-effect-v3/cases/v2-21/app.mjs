import { createServer } from "node:http";

const PORT = __PORT__;
const STRINGS = {
  en: { title: "Release notes", published: "Published", language: "Language", subscribe: "Subscribe to updates", body: "Version 3.2 adds offline mode and faster sync." },
  de: { title: "Versionshinweise", published: "Veröffentlicht", language: "Sprache", subscribe: "Updates abonnieren", body: "Version 3.2 bringt einen Offline-Modus und schnellere Synchronisierung." },
};
const PUBLISHED_AT = "2026-10-05T12:00:00Z";
let language = "en";

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));
const readJson = async (req) => {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Release notes</title></head>
<body>
  <main>
    <div id="ln-switcher">
      <label for="ln-language" id="ln-language-label">Language</label>
      <select id="ln-language" name="language">
        <option value="en">English</option>
        <option value="de">Deutsch</option>
      </select>
    </div>
    <h1 id="ln-title"></h1>
    <p id="ln-published"></p>
    <p id="ln-body"></p>
    <button type="button" id="ln-subscribe"></button>
  </main>
  <script>
    const STRINGS = ${JSON.stringify(STRINGS)};
    const PUBLISHED_AT = ${JSON.stringify(PUBLISHED_AT)};
    const el = (id) => document.getElementById(id);

    function apply(code) {
      const t = STRINGS[code];
      document.documentElement.lang = code;
      el("ln-language-label").textContent = t.language;
      el("ln-title").textContent = t.title;
      el("ln-body").textContent = t.body;
      el("ln-subscribe").textContent = t.subscribe;
      const date = new Date(PUBLISHED_AT).toLocaleDateString(code, { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
      el("ln-published").textContent = t.published + ": " + date;
      el("ln-language").value = code;
    }

    el("ln-language").addEventListener("change", async () => {
      const code = el("ln-language").value;
      await fetch("/api/language", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ language: code }) });
      apply(code);
    });

    fetch("/api/language").then((r) => r.json()).then((data) => apply(data.language));
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/language" && req.method === "GET") return json(res, 200, { language });
    if (url.pathname === "/api/language" && req.method === "PUT") {
      const body = await readJson(req);
      if (!STRINGS[body.language]) return json(res, 400, { error: "Unknown language" });
      language = body.language;
      return json(res, 200, { language });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      language = "en";
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
