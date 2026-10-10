import { createServer } from "node:http";

const PORT = __PORT__;
const PLANTS = ["Tomato", "Basil", "Kale", "Zucchini"];
const NEEDS_WATER_AFTER_DAYS = 3;
const seed = () => [
  { id: 1, name: "Bed 1", plant: "Tomato", daysSinceWater: 1 },
  { id: 2, name: "Bed 2", plant: "Basil", daysSinceWater: 4 },
  { id: 3, name: "Bed 3", plant: "Kale", daysSinceWater: 3 },
  { id: 4, name: "Bed 4", plant: "Zucchini", daysSinceWater: 0 },
];
let beds = seed();

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
<head><meta charset="utf-8"><title>Garden planner</title></head>
<body>
  <main>
    <h1>Garden planner</h1>
    <p id="gp-summary" class="summary-line"></p>
    <div id="gp-filter-row" class="filter-row">
      <input type="checkbox" id="gp-needs-only">
      <label for="gp-needs-only">Show only beds that need water</label>
    </div>
    <div id="gp-beds" class="beds"></div>
    <p id="gp-all-watered" class="all-watered" hidden>All beds are watered</p>
  </main>
  <script>
    const PLANTS = ${JSON.stringify(PLANTS)};
    const THRESHOLD = ${NEEDS_WATER_AFTER_DAYS};
    const el = (id) => document.getElementById(id);
    let state = [];
    const needsWater = (bed) => bed.daysSinceWater >= THRESHOLD;
    const lastWatered = (bed) => bed.daysSinceWater === 0 ? "today" : bed.daysSinceWater === 1 ? "yesterday" : bed.daysSinceWater + " days ago";

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function card(bed) {
      const article = document.createElement("article");
      article.className = needsWater(bed) ? "bed thirsty" : "bed";
      const heading = document.createElement("h2");
      heading.textContent = bed.name;
      const select = document.createElement("select");
      select.setAttribute("aria-label", "Plant for " + bed.name);
      for (const p of PLANTS) {
        const option = document.createElement("option");
        option.value = p;
        option.textContent = p;
        option.selected = p === bed.plant;
        select.append(option);
      }
      select.addEventListener("change", async () => {
        const updated = await api("PATCH", "/api/beds/" + bed.id, { plant: select.value });
        if (!updated) return;
        state = state.map((b) => (b.id === updated.id ? updated : b));
        render();
      });
      const watered = document.createElement("p");
      watered.className = "watered-line";
      watered.textContent = "Last watered: " + lastWatered(bed);
      const badge = document.createElement("span");
      badge.className = "badge-thirsty";
      badge.textContent = "Needs water";
      badge.hidden = !needsWater(bed);
      const water = document.createElement("button");
      water.type = "button";
      water.textContent = "Water";
      water.setAttribute("aria-label", "Water " + bed.name);
      water.addEventListener("click", async () => {
        const updated = await api("POST", "/api/beds/" + bed.id + "/water");
        if (!updated) return;
        state = state.map((b) => (b.id === updated.id ? updated : b));
        render();
      });
      article.append(heading, select, watered, badge, water);
      return article;
    }

    function render() {
      const only = el("gp-needs-only").checked;
      const visible = only ? state.filter(needsWater) : state;
      el("gp-beds").replaceChildren(...visible.map(card));
      const thirsty = state.filter(needsWater).length;
      el("gp-summary").textContent = thirsty === 0 ? "No beds need water" : thirsty + (thirsty === 1 ? " bed needs water" : " beds need water");
      el("gp-all-watered").hidden = !(only && visible.length === 0);
    }

    el("gp-needs-only").addEventListener("change", render);
    api("GET", "/api/beds").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/beds" && req.method === "GET") return json(res, 200, beds);
    const water = url.pathname.match(/^\/api\/beds\/(\d+)\/water$/);
    if (water && req.method === "POST") {
      const bed = beds.find((b) => b.id === Number(water[1]));
      if (!bed) return json(res, 404, { error: "Not found" });
      bed.daysSinceWater = 0;
      return json(res, 200, bed);
    }
    const match = url.pathname.match(/^\/api\/beds\/(\d+)$/);
    if (match && req.method === "PATCH") {
      const bed = beds.find((b) => b.id === Number(match[1]));
      if (!bed) return json(res, 404, { error: "Not found" });
      const { plant } = await readJson(req);
      if (!PLANTS.includes(plant)) return json(res, 400, { error: "Unknown plant" });
      bed.plant = plant;
      return json(res, 200, bed);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      beds = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
