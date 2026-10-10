import { createServer } from "node:http";

const PORT = __PORT__;
const ROWS = ["A", "B", "C"];
const COLS = [1, 2, 3, 4];
const MAX_SELECT = 4;
const seed = () => ({ taken: ["A1", "B3", "C4"] });
let state = seed();

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
<head><meta charset="utf-8"><title>Seat picker</title></head>
<body>
  <main>
    <h1>Pick your seats</h1>
    <p id="sp-legend" class="legend">Selected 0 · Available 0 · Taken 0</p>
    <p id="sp-selected" class="selected-line">Selected: none</p>
    <p id="sp-message" class="message"></p>
    <div id="sp-grid" class="grid"></div>
    <button type="button" id="sp-reserve" disabled>Reserve</button>
    <p id="sp-confirmation" class="confirmation"></p>
  </main>
  <script>
    const ROWS = ${JSON.stringify(ROWS)};
    const COLS = ${JSON.stringify(COLS)};
    const MAX_SELECT = ${MAX_SELECT};
    const el = (id) => document.getElementById(id);
    let taken = [];
    let selected = [];

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function render() {
      el("sp-grid").replaceChildren(...ROWS.map((row) => {
        const line = document.createElement("div");
        line.className = "seat-row";
        for (const col of COLS) {
          const id = row + col;
          const seat = document.createElement("button");
          seat.type = "button";
          seat.className = taken.includes(id) ? "seat taken" : selected.includes(id) ? "seat picked" : "seat";
          seat.textContent = id;
          seat.setAttribute("aria-label", "Seat " + id);
          seat.setAttribute("aria-pressed", String(selected.includes(id)));
          seat.disabled = taken.includes(id);
          seat.addEventListener("click", () => toggle(id));
          line.append(seat);
        }
        return line;
      }));
      const total = ROWS.length * COLS.length;
      el("sp-legend").textContent = "Selected " + selected.length + " · Available " + (total - taken.length - selected.length) + " · Taken " + taken.length;
      el("sp-selected").textContent = "Selected: " + (selected.length ? selected.join(", ") : "none");
      el("sp-reserve").disabled = selected.length === 0;
    }

    function toggle(id) {
      el("sp-message").textContent = "";
      if (selected.includes(id)) {
        selected = selected.filter((s) => s !== id);
      } else if (selected.length >= MAX_SELECT) {
        el("sp-message").textContent = "You can pick up to " + MAX_SELECT + " seats";
      } else {
        selected = [...selected, id];
      }
      render();
    }

    el("sp-reserve").addEventListener("click", async () => {
      const result = await api("POST", "/api/reservations", { seats: selected });
      if (!result) return;
      taken = result.taken;
      el("sp-confirmation").textContent = "Reserved " + selected.join(", ");
      selected = [];
      render();
    });

    api("GET", "/api/seats").then((data) => { taken = data.taken; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/seats" && req.method === "GET") return json(res, 200, state);
    if (url.pathname === "/api/reservations" && req.method === "POST") {
      const { seats = [] } = await readJson(req);
      if (!Array.isArray(seats) || seats.length === 0 || seats.length > MAX_SELECT) return json(res, 400, { error: "Pick 1 to 4 seats" });
      if (seats.some((s) => state.taken.includes(s))) return json(res, 409, { error: "Seat already taken" });
      state.taken = [...state.taken, ...seats];
      return json(res, 201, state);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      state = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
