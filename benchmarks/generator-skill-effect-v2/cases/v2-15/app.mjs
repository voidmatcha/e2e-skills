import { createServer } from "node:http";

const PORT = __PORT__;
const COUNTRIES = {
  CA: { name: "Canada", regions: ["Alberta", "British Columbia", "Ontario", "Quebec"], postal: /^[A-Za-z]\d[A-Za-z] \d[A-Za-z]\d$/ },
  DE: { name: "Germany", regions: ["Bavaria", "Berlin", "Hamburg", "Saxony"], postal: /^\d{5}$/ },
  US: { name: "United States", regions: ["California", "New York", "Texas", "Washington"], postal: /^\d{5}$/ },
};
let addresses = [];
let nextId = 1;

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
<head><meta charset="utf-8"><title>Address book</title></head>
<body>
  <main>
    <h1>Address book</h1>
    <form id="ab-form">
      <label for="ab-country">Country</label>
      <select id="ab-country" name="country">
        <option value="">Choose a country</option>
        ${Object.entries(COUNTRIES).map(([code, c]) => `<option value="${code}">${c.name}</option>`).join("")}
      </select>
      <label for="ab-region">Region</label>
      <select id="ab-region" name="region" disabled><option value="">Choose a region</option></select>
      <label for="ab-postal">Postal code</label>
      <input id="ab-postal" name="postal" autocomplete="off">
      <button type="submit">Save address</button>
    </form>
    <p id="ab-error" role="alert"></p>
    <ul id="ab-list" aria-label="Saved addresses"></ul>
  </main>
  <script>
    const COUNTRIES = ${JSON.stringify(Object.fromEntries(Object.entries(COUNTRIES).map(([k, v]) => [k, { name: v.name, regions: v.regions }])))};
    const el = (id) => document.getElementById(id);
    let state = [];

    function fillRegions(code) {
      const select = el("ab-region");
      select.replaceChildren();
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Choose a region";
      select.append(placeholder);
      for (const region of (COUNTRIES[code] ? COUNTRIES[code].regions : [])) {
        const option = document.createElement("option");
        option.value = region;
        option.textContent = region;
        select.append(option);
      }
      select.value = "";
      select.disabled = !COUNTRIES[code];
    }

    function render() {
      el("ab-list").replaceChildren(...state.map((address) => {
        const li = document.createElement("li");
        li.className = address.isDefault ? "address default" : "address";
        const text = document.createElement("span");
        text.textContent = address.region + ", " + COUNTRIES[address.country].name + " " + address.postal + (address.isDefault ? " (default)" : "");
        li.append(text);
        if (!address.isDefault) {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = "Set as default";
          button.setAttribute("aria-label", "Set " + address.region + " as default");
          button.addEventListener("click", async () => {
            const res = await fetch("/api/addresses/" + address.id + "/default", { method: "POST" });
            if (!res.ok) return;
            for (const a of state) a.isDefault = a.id === address.id;
            render();
          });
          li.append(button);
        }
        return li;
      }));
    }

    el("ab-country").addEventListener("change", () => fillRegions(el("ab-country").value));
    el("ab-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      el("ab-error").textContent = "";
      const payload = { country: el("ab-country").value, region: el("ab-region").value, postal: el("ab-postal").value.trim() };
      for (const field of el("ab-form").elements) field.disabled = true;
      const res = await fetch("/api/addresses", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
      const body = await res.json();
      for (const field of el("ab-form").elements) field.disabled = false;
      el("ab-region").disabled = !COUNTRIES[el("ab-country").value];
      if (!res.ok) {
        el("ab-error").textContent = body.error;
        return;
      }
      state.push(body);
      el("ab-form").reset();
      fillRegions("");
      render();
    });

    fetch("/api/addresses").then((r) => r.json()).then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/addresses" && req.method === "GET") return json(res, 200, addresses);
    if (url.pathname === "/api/addresses" && req.method === "POST") {
      const { country, region, postal = "" } = await readJson(req);
      const spec = COUNTRIES[country];
      if (!spec) return json(res, 400, { error: "Choose a country" });
      if (!spec.regions.includes(region)) return json(res, 400, { error: "Choose a region" });
      if (!spec.postal.test(String(postal))) return json(res, 400, { error: "Enter a valid postal code for " + spec.name });
      const address = { id: nextId++, country, region, postal: String(postal), isDefault: addresses.length === 0 };
      addresses.push(address);
      return json(res, 201, address);
    }
    const match = url.pathname.match(/^\/api\/addresses\/(\d+)\/default$/);
    if (match && req.method === "POST") {
      const target = addresses.find((a) => a.id === Number(match[1]));
      if (!target) return json(res, 404, { error: "Not found" });
      for (const a of addresses) a.isDefault = false;
      target.isDefault = true;
      return json(res, 200, target);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      addresses = [];
      nextId = 1;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
