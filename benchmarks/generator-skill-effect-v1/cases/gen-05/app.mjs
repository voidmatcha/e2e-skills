import { createServer } from "node:http";

const PORT = __PORT__;
const defaults = { theme: "light", language: "en" };
let prefs = { ...defaults };

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
<html lang="en" data-theme="light">
<head><meta charset="utf-8"><title>Preferences</title></head>
<body>
  <main>
    <h1>Preferences</h1>
    <form id="pf-form">
      <div id="pf-theme-row">
        <input type="checkbox" id="pf-dark" name="dark">
        <label for="pf-dark">Dark mode</label>
      </div>
      <div id="pf-language-row">
        <label for="pf-language">Language</label>
        <select id="pf-language" name="language">
          <option value="en">English</option>
          <option value="de">Deutsch</option>
          <option value="fr">Français</option>
        </select>
      </div>
      <button type="button" id="pf-save">Save</button>
    </form>
    <p id="pf-status" role="status"></p>
  </main>
  <script>
    const darkEl = document.getElementById("pf-dark");
    const languageEl = document.getElementById("pf-language");
    const saveEl = document.getElementById("pf-save");
    const statusEl = document.getElementById("pf-status");

    function applyTheme() {
      document.documentElement.dataset.theme = darkEl.checked ? "dark" : "light";
    }

    function clearStatus() {
      statusEl.textContent = "";
    }

    function show(saved) {
      darkEl.checked = saved.theme === "dark";
      languageEl.value = saved.language;
      applyTheme();
    }

    async function save() {
      const res = await fetch("/api/preferences", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ theme: darkEl.checked ? "dark" : "light", language: languageEl.value }),
      });
      if (res.ok) statusEl.textContent = "Preferences saved";
    }

    darkEl.addEventListener("change", () => {
      applyTheme();
      clearStatus();
    });
    languageEl.addEventListener("change", clearStatus);
    saveEl.addEventListener("click", save);

    fetch("/api/preferences").then((r) => r.json()).then(show);
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/preferences" && req.method === "GET") return json(res, 200, prefs);
    if (url.pathname === "/api/preferences" && req.method === "PUT") {
      const body = await readJson(req);
      const theme = body.theme === "dark" ? "dark" : "light";
      const language = ["en", "de", "fr"].includes(body.language) ? body.language : prefs.language;
      prefs = { theme, language };
      return json(res, 200, prefs);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      prefs = { ...defaults };
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
