import { createServer } from "node:http";

const PORT = __PORT__;

const products = [
  { id: 1, name: "Alpine Jacket", price: 120 },
  { id: 2, name: "Trail Runner Shoes", price: 90 },
  { id: 3, name: "Canvas Tote", price: 25 },
  { id: 4, name: "Merino Beanie", price: 30 },
  { id: 5, name: "Rain Shell", price: 150 },
  { id: 6, name: "Camp Mug", price: 12 },
];

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Products</title></head>
<body>
  <main>
    <h1>Products</h1>
    <div id="ps-toolbar">
      <label for="ps-query">Search products</label>
      <input id="ps-query" name="query" autocomplete="off">
      <button type="button" id="ps-clear">Clear</button>
    </div>
    <p id="ps-count" aria-live="polite"></p>
    <ul id="ps-list" aria-label="Products"></ul>
    <p id="ps-empty" hidden>No products match</p>
  </main>
  <script>
    const products = ${JSON.stringify(products)};
    const queryEl = document.getElementById("ps-query");
    const clearEl = document.getElementById("ps-clear");
    const countEl = document.getElementById("ps-count");
    const listEl = document.getElementById("ps-list");
    const emptyEl = document.getElementById("ps-empty");

    function matching(query) {
      const q = query.trim();
      if (!q) return products;
      return products.filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));
    }

    function render(matches) {
      listEl.replaceChildren();
      for (const p of matches) {
        const li = document.createElement("li");
        li.className = "product";
        li.textContent = p.name + " — $" + p.price;
        listEl.append(li);
      }
      countEl.textContent = "Showing " + matches.length + " of " + products.length + " products";
      emptyEl.hidden = matches.length > 0;
    }

    function apply() {
      render(matching(queryEl.value));
    }

    queryEl.addEventListener("input", apply);
    clearEl.addEventListener("click", () => {
      queryEl.value = "";
      apply();
    });
    apply();
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/products") return send(res, 200, "application/json", JSON.stringify(products));
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
