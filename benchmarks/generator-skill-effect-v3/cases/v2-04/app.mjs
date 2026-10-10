import { createServer } from "node:http";

const PORT = __PORT__;
const defaults = { displayName: "Ada", bio: "", emailAlerts: false, digest: "weekly" };
let settings = { ...defaults };

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
<head><meta charset="utf-8"><title>Account settings</title></head>
<body>
  <main>
    <h1>Account settings</h1>
    <div role="tablist" aria-label="Settings sections" id="st-tabs">
      <button type="button" role="tab" id="st-tab-profile" aria-selected="true" aria-controls="st-panel-profile">Profile</button>
      <button type="button" role="tab" id="st-tab-notifications" aria-selected="false" aria-controls="st-panel-notifications">Notifications</button>
    </div>
    <div id="st-guard" role="alertdialog" aria-label="Unsaved changes" hidden>
      <p>You have unsaved changes</p>
      <button type="button" id="st-discard">Discard</button>
      <button type="button" id="st-keep">Keep editing</button>
    </div>
    <section id="st-panel-profile" role="tabpanel" aria-labelledby="st-tab-profile">
      <label for="st-display-name">Display name</label>
      <input id="st-display-name" name="displayName" autocomplete="off">
      <label for="st-bio">Bio</label>
      <input id="st-bio" name="bio" autocomplete="off">
    </section>
    <section id="st-panel-notifications" role="tabpanel" aria-labelledby="st-tab-notifications" hidden>
      <input type="checkbox" id="st-email-alerts" name="emailAlerts">
      <label for="st-email-alerts">Email alerts</label>
      <label for="st-digest">Digest</label>
      <select id="st-digest" name="digest">
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="never">Never</option>
      </select>
    </section>
    <div id="st-actions">
      <button type="button" id="st-reset">Reset</button>
      <button type="button" id="st-save" disabled>Save</button>
    </div>
    <p id="st-status" role="status"></p>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    const fields = { displayName: el("st-display-name"), bio: el("st-bio"), emailAlerts: el("st-email-alerts"), digest: el("st-digest") };
    const tabs = { profile: el("st-tab-profile"), notifications: el("st-tab-notifications") };
    const panels = { profile: el("st-panel-profile"), notifications: el("st-panel-notifications") };
    let saved = null;
    let pendingTab = null;

    function current() {
      return { displayName: fields.displayName.value, bio: fields.bio.value, emailAlerts: fields.emailAlerts.checked, digest: fields.digest.value };
    }
    function isDirty() {
      const now = current();
      return Object.keys(saved).some((key) => saved[key] !== now[key]);
    }
    function fill(values) {
      fields.displayName.value = values.displayName;
      fields.bio.value = values.bio;
      fields.emailAlerts.checked = values.emailAlerts;
      fields.digest.value = values.digest;
      refresh();
    }
    function refresh() {
      el("st-save").disabled = !isDirty();
    }
    function switchTo(name) {
      for (const [key, tab] of Object.entries(tabs)) {
        tab.setAttribute("aria-selected", String(key === name));
        panels[key].hidden = key !== name;
      }
    }
    function requestSwitch(name) {
      if (tabs[name].getAttribute("aria-selected") === "true") return;
      if (isDirty()) {
        pendingTab = name;
        el("st-guard").hidden = false;
        return;
      }
      switchTo(name);
    }

    for (const [name, tab] of Object.entries(tabs)) tab.addEventListener("click", () => requestSwitch(name));
    el("st-discard").addEventListener("click", () => {
      el("st-guard").hidden = true;
      fill(saved);
      switchTo(pendingTab);
      pendingTab = null;
    });
    el("st-keep").addEventListener("click", () => {
      el("st-guard").hidden = true;
      pendingTab = null;
    });
    for (const field of Object.values(fields)) {
      field.addEventListener("input", () => { el("st-status").textContent = ""; refresh(); });
      field.addEventListener("change", () => { el("st-status").textContent = ""; refresh(); });
    }
    el("st-reset").addEventListener("click", () => fill(saved));
    el("st-save").addEventListener("click", async () => {
      const payload = current();
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) return;
      saved = await res.json();
      el("st-status").textContent = "Settings saved";
      refresh();
    });

    fetch("/api/settings").then((r) => r.json()).then((values) => { saved = values; fill(values); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/settings" && req.method === "GET") return json(res, 200, settings);
    if (url.pathname === "/api/settings" && req.method === "PUT") {
      const body = await readJson(req);
      settings = {
        displayName: String(body.displayName ?? defaults.displayName),
        bio: String(body.bio ?? defaults.bio),
        emailAlerts: Boolean(body.emailAlerts ?? defaults.emailAlerts),
        digest: ["daily", "weekly", "never"].includes(body.digest) ? body.digest : defaults.digest,
      };
      return json(res, 200, settings);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      settings = { ...defaults };
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
