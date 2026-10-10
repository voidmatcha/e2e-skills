import { createServer } from "node:http";

const PORT = __PORT__;
const ORDERS = [
  { id: "1001", customer: "Ada", status: "paid" },
  { id: "1002", customer: "Grace", status: "shipped" },
  { id: "1003", customer: "Linus", status: "refunded" },
  { id: "1010", customer: "Margaret", status: "shipped" },
  { id: "1011", customer: "Ken", status: "paid" },
  { id: "1020", customer: "Barbara", status: "shipped" },
  { id: "2001", customer: "Dennis", status: "paid" },
  { id: "2010", customer: "Radia", status: "refunded" },
];

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Orders</title></head>
<body>
  <main>
    <h1>Orders</h1>
    <form id="or-filters">
      <label for="or-status">Status</label>
      <select id="or-status" name="status">
        <option value="">Any status</option>
        <option value="paid">Paid</option>
        <option value="shipped">Shipped</option>
        <option value="refunded">Refunded</option>
      </select>
      <label for="or-search">Search</label>
      <input id="or-search" name="q" autocomplete="off" placeholder="Order number">
      <button type="button" id="or-clear">Clear filters</button>
    </form>
    <p id="or-count" aria-live="polite"></p>
    <ul id="or-list" aria-label="Orders"></ul>
  </main>
  <script>
    const ORDERS = ${JSON.stringify(ORDERS)};
    const el = (id) => document.getElementById(id);

    function readUrl() {
      const params = new URLSearchParams(location.search);
      el("or-status").value = params.get("status") || "";
      el("or-search").value = params.get("q") || "";
    }

    function writeUrl() {
      const params = new URLSearchParams();
      if (el("or-status").value) params.set("status", el("or-status").value);
      if (el("or-search").value.trim()) params.set("q", el("or-search").value.trim());
      const query = params.toString();
      history.replaceState(null, "", query ? "?" + query : location.pathname);
    }

    function render() {
      const status = el("or-status").value;
      const q = el("or-search").value.trim();
      const matches = ORDERS.filter((o) => (!status || o.status === status) && (!q || o.id.includes(q)));
      el("or-list").replaceChildren(...matches.map((o) => {
        const li = document.createElement("li");
        li.textContent = "#" + o.id + " — " + o.customer + " — " + o.status;
        return li;
      }));
      el("or-count").textContent = matches.length === 1 ? "1 order" : matches.length + " orders";
    }

    function update() {
      writeUrl();
      render();
    }

    el("or-status").addEventListener("change", update);
    el("or-search").addEventListener("input", update);
    el("or-clear").addEventListener("click", () => {
      el("or-status").value = "";
      el("or-search").value = "";
      update();
    });

    readUrl();
    render();
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/orders" && req.method === "GET") return send(res, 200, "application/json", JSON.stringify(ORDERS));
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
