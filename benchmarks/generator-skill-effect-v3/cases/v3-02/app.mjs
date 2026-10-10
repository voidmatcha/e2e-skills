import { createServer } from "node:http";

const PORT = __PORT__;
const RECIPES = [
  { id: "soup", name: "Lentil soup", tags: ["vegan", "quick"] },
  { id: "curry", name: "Chickpea curry", tags: ["vegan"] },
  { id: "omelette", name: "Herb omelette", tags: ["quick"] },
  { id: "lasagne", name: "Mushroom lasagne", tags: ["bake"] },
];
const seed = () => Object.fromEntries(RECIPES.map((r) => [r.id, { servings: 2, planned: false }]));
let plan = seed();

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
<head><meta charset="utf-8"><title>Recipes</title></head>
<body>
  <main>
    <h1>Recipes</h1>
    <p id="rc-plan" class="plan-line">Plan: 0 recipes · 0 servings</p>
    <div id="rc-tags" class="chips"></div>
    <div id="rc-cards" class="cards"></div>
    <p id="rc-empty" class="empty" hidden>No recipes match</p>
  </main>
  <script>
    const RECIPES = ${JSON.stringify(RECIPES)};
    const el = (id) => document.getElementById(id);
    let state = {};
    let tag = null;

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function renderTags() {
      const tags = [...new Set(RECIPES.flatMap((r) => r.tags))];
      el("rc-tags").replaceChildren(...tags.map((t) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = tag === t ? "chip chip-on" : "chip";
        chip.textContent = t;
        chip.setAttribute("aria-pressed", String(tag === t));
        chip.addEventListener("click", () => { tag = tag === t ? null : t; render(); });
        return chip;
      }));
    }

    function card(recipe) {
      const entry = state[recipe.id];
      const article = document.createElement("article");
      article.className = entry.planned ? "card planned" : "card";
      const heading = document.createElement("h2");
      heading.textContent = recipe.name;
      const tags = document.createElement("p");
      tags.className = "tags";
      tags.textContent = recipe.tags.join(", ");
      const servings = document.createElement("span");
      servings.className = "servings";
      servings.textContent = entry.servings + (entry.servings === 1 ? " serving" : " servings");
      const fewer = document.createElement("button");
      fewer.type = "button";
      fewer.textContent = "−";
      fewer.setAttribute("aria-label", "Fewer servings for " + recipe.name);
      fewer.addEventListener("click", () => setServings(recipe.id, entry.servings - 1));
      const more = document.createElement("button");
      more.type = "button";
      more.textContent = "+";
      more.setAttribute("aria-label", "More servings for " + recipe.name);
      more.addEventListener("click", () => setServings(recipe.id, entry.servings + 1));
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.textContent = entry.planned ? "Remove from plan" : "Add to plan";
      toggle.setAttribute("aria-label", (entry.planned ? "Remove " : "Add ") + recipe.name + (entry.planned ? " from plan" : " to plan"));
      toggle.setAttribute("aria-pressed", String(entry.planned));
      toggle.addEventListener("click", async () => {
        const updated = await api("PATCH", "/api/plan/" + recipe.id, { planned: !entry.planned });
        if (!updated) return;
        state[recipe.id] = updated;
        render();
      });
      const controls = document.createElement("div");
      controls.className = "controls";
      controls.append(fewer, servings, more, toggle);
      article.append(heading, tags, controls);
      return article;
    }

    async function setServings(id, value) {
      const next = Math.max(1, value);
      const updated = await api("PATCH", "/api/plan/" + id, { servings: next });
      if (!updated) return;
      state[id] = updated;
      render();
    }

    function render() {
      renderTags();
      const visible = tag ? RECIPES.filter((r) => r.tags.includes(tag)) : RECIPES;
      el("rc-cards").replaceChildren(...visible.map(card));
      el("rc-empty").hidden = visible.length > 0;
      const planned = RECIPES.filter((r) => state[r.id].planned);
      const servings = planned.reduce((sum, r) => sum + state[r.id].servings, 0);
      el("rc-plan").textContent = "Plan: " + planned.length + (planned.length === 1 ? " recipe" : " recipes") + " · " + servings + " servings";
    }

    api("GET", "/api/plan").then((data) => { state = data; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/plan" && req.method === "GET") return json(res, 200, plan);
    const match = url.pathname.match(/^\/api\/plan\/([a-z]+)$/);
    if (match && req.method === "PATCH") {
      const entry = plan[match[1]];
      if (!entry) return json(res, 404, { error: "Unknown recipe" });
      const body = await readJson(req);
      if (typeof body.planned === "boolean") entry.planned = body.planned;
      if (typeof body.servings === "number") entry.servings = Math.max(1, Math.round(body.servings));
      return json(res, 200, entry);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      plan = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
