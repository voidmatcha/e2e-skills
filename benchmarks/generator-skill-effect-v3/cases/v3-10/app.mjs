import { createServer } from "node:http";

const PORT = __PORT__;
const STEPS = ["Ordered", "Packed", "Shipped", "Out for delivery", "Delivered"];
const seed = () => ({ step: 1, cancelled: false });
let order = seed();

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Order tracking</title></head>
<body>
  <main>
    <h1>Order #48213</h1>
    <p id="ot-header" class="header-line"></p>
    <p id="ot-eta" class="eta">Estimated delivery: Thursday 9 October</p>
    <ol id="ot-steps" class="timeline" aria-label="Timeline"></ol>
    <div id="ot-actions" class="actions">
      <button type="button" id="ot-cancel">Cancel order</button>
      <button type="button" id="ot-advance" class="dev">Advance (test seam)</button>
    </div>
    <p id="ot-cancelled" class="cancelled" hidden>Cancelled</p>
  </main>
  <script>
    const STEPS = ${JSON.stringify(STEPS)};
    const SHIPPED = 3;
    const el = (id) => document.getElementById(id);
    let state = { step: 1, cancelled: false };

    async function api(method, path) {
      const res = await fetch(path, { method });
      return res.ok ? res.json() : null;
    }

    function render() {
      el("ot-steps").replaceChildren(...STEPS.map((name, i) => {
        const index = i + 1;
        const li = document.createElement("li");
        let status = "Upcoming";
        if (!state.cancelled) {
          if (index < state.step) status = "Done";
          else if (index === state.step) status = "Current";
        } else if (index < state.step) {
          status = "Done";
        }
        li.className = "step step-" + status.toLowerCase();
        const label = document.createElement("span");
        label.className = "step-name";
        label.textContent = name;
        const badge = document.createElement("span");
        badge.className = "step-status";
        badge.textContent = status;
        li.append(label, " — ", badge);
        return li;
      }));
      el("ot-header").textContent = state.cancelled ? "Order cancelled" : "Step " + state.step + " of " + STEPS.length + ": " + STEPS[state.step - 1];
      el("ot-cancel").hidden = state.cancelled || state.step >= SHIPPED;
      el("ot-advance").hidden = state.cancelled || state.step >= STEPS.length;
      el("ot-cancelled").hidden = !state.cancelled;
      el("ot-eta").hidden = state.cancelled;
    }

    el("ot-advance").addEventListener("click", async () => {
      const next = await api("POST", "/api/dev/advance");
      if (!next) return;
      state = next;
      render();
    });
    el("ot-cancel").addEventListener("click", async () => {
      const next = await api("POST", "/api/order/cancel");
      if (!next) return;
      state = next;
      render();
    });

    api("GET", "/api/order").then((data) => { state = data; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/order" && req.method === "GET") return json(res, 200, order);
    if (url.pathname === "/api/dev/advance" && req.method === "POST") {
      if (order.cancelled) return json(res, 409, { error: "Order is cancelled" });
      if (order.step < STEPS.length) order.step += 1;
      return json(res, 200, order);
    }
    if (url.pathname === "/api/order/cancel" && req.method === "POST") {
      if (order.step >= 3) return json(res, 409, { error: "Too late to cancel" });
      order.cancelled = true;
      return json(res, 200, order);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      order = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
