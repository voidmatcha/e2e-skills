import { createServer } from "node:http";

const PORT = __PORT__;
const ROWS = [
  { name: "Anvil", price: 120, stock: 2 },
  { name: "Bellows", price: 42, stock: 0 },
  { name: "Chisel set", price: 15, stock: 14 },
  { name: "Drawknife", price: 68, stock: 1 },
  { name: "Emery cloth", price: 7, stock: 0 },
  { name: "Froe", price: 9.5, stock: 6 },
];

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Inventory</title></head>
<body>
  <main>
    <h1>Inventory</h1>
    <table id="iv-table">
      <thead>
        <tr>
          <th scope="col" aria-sort="none"><button type="button" id="iv-sort-name" data-key="name">Name</button></th>
          <th scope="col" aria-sort="none"><button type="button" id="iv-sort-price" data-key="price">Price</button></th>
          <th scope="col" aria-sort="none"><button type="button" id="iv-sort-stock" data-key="stock">Stock</button></th>
        </tr>
      </thead>
      <tbody id="iv-rows"></tbody>
    </table>
  </main>
  <script>
    const rows = ${JSON.stringify(ROWS)};
    const money = (n) => "$" + n.toFixed(2);
    const state = { sort: null, dir: "asc" };

    function readUrl() {
      const params = new URLSearchParams(location.search);
      const sort = params.get("sort");
      if (["name", "price", "stock"].includes(sort)) {
        state.sort = sort;
        state.dir = params.get("dir") === "desc" ? "desc" : "asc";
      }
    }

    function writeUrl() {
      const params = new URLSearchParams();
      if (state.sort) {
        params.set("sort", state.sort);
        params.set("dir", state.dir);
      }
      const query = params.toString();
      history.replaceState(null, "", query ? "?" + query : location.pathname);
    }

    function compare(a, b) {
      const key = state.sort;
      const result = typeof a[key] === "number" ? a[key] - b[key] : a[key].localeCompare(b[key]);
      return state.dir === "desc" ? -result : result;
    }

    function render() {
      const ordered = state.sort ? [...rows].sort(compare) : rows;
      document.getElementById("iv-rows").replaceChildren(...ordered.map((row) => {
        const tr = document.createElement("tr");
        const name = document.createElement("td");
        name.textContent = row.name;
        if (row.stock === 0) {
          const badge = document.createElement("span");
          badge.className = "badge";
          badge.textContent = "Out of stock";
          name.append(" ", badge);
        }
        const price = document.createElement("td");
        price.textContent = money(row.price);
        const stock = document.createElement("td");
        stock.textContent = String(row.stock);
        tr.append(name, price, stock);
        return tr;
      }));
      for (const th of document.querySelectorAll("th")) {
        const key = th.querySelector("button").dataset.key;
        th.setAttribute("aria-sort", key === state.sort ? (state.dir === "asc" ? "ascending" : "descending") : "none");
      }
    }

    for (const button of document.querySelectorAll("th button")) {
      button.addEventListener("click", () => {
        const key = button.dataset.key;
        if (state.sort === key) state.dir = state.dir === "asc" ? "desc" : "asc";
        else { state.sort = key; state.dir = "asc"; }
        writeUrl();
        render();
      });
    }

    readUrl();
    render();
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/inventory" && req.method === "GET") return send(res, 200, "application/json", JSON.stringify(ROWS));
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
