import { createServer } from "node:http";

const PORT = __PORT__;
const PRODUCTS = [
  { id: 1, name: "Field Notebook", price: 9.5 },
  { id: 2, name: "Brass Compass", price: 42 },
  { id: 3, name: "Wool Blanket", price: 68 },
];
let wishlist = [];

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));
const money = (n) => "$" + n.toFixed(2);
const escape = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const layout = (title, body, count) => `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>${escape(title)} — Outfitters</title></head>
<body>
  <header id="sf-header">
    <a href="/" id="sf-home">Outfitters</a>
    <a href="/wishlist" id="sf-wishlist-link">Wishlist (<span id="sf-wishlist-count">${count}</span>)</a>
  </header>
  <main id="sf-main">
    ${body}
  </main>
</body>
</html>`;

const listPage = () => layout("Products", `
    <h1>Products</h1>
    <ul id="sf-products" aria-label="Products">
      ${PRODUCTS.map((p) => `<li class="product"><a href="/products/${p.id}">${escape(p.name)}</a> <span class="price">${money(p.price)}</span></li>`).join("\n      ")}
    </ul>`, wishlist.length);

const detailPage = (product) => layout(product.name, `
    <h1 id="sf-product-name">${escape(product.name)}</h1>
    <p id="sf-product-price">${money(product.price)}</p>
    <button type="button" id="sf-add" data-id="${product.id}">Add to wishlist</button>
    <p id="sf-status" role="status"></p>
    <p><a href="/">Back to products</a></p>
    <script>
      document.getElementById("sf-add").addEventListener("click", async () => {
        const res = await fetch("/api/wishlist", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ id: ${product.id} }) });
        const body = await res.json();
        document.getElementById("sf-status").textContent = body.added ? "Added to your wishlist" : "Already in your wishlist";
        document.getElementById("sf-wishlist-count").textContent = body.count;
      });
    </script>`, wishlist.length);

const notFoundPage = () => layout("Not found", `
    <h1>Product not found</h1>
    <p><a href="/">Back to products</a></p>`, wishlist.length);

const wishlistPage = () => layout("Wishlist", `
    <h1>Wishlist</h1>
    <ul id="sf-saved" aria-label="Saved products">
      ${wishlist.map((id) => PRODUCTS.find((p) => p.id === id)).map((p) => `<li class="saved" data-id="${p.id}"><a href="/products/${p.id}">${escape(p.name)}</a> <span class="price">${money(p.price)}</span> <button type="button" class="remove" aria-label="Remove ${escape(p.name)}" data-id="${p.id}">Remove</button></li>`).join("\n      ")}
    </ul>
    <p id="sf-empty" ${wishlist.length ? "hidden" : ""}>Your wishlist is empty</p>
    <script>
      for (const button of document.querySelectorAll("button.remove")) {
        button.addEventListener("click", async () => {
          await fetch("/api/wishlist/" + button.dataset.id, { method: "DELETE" });
          button.closest("li").remove();
          const left = document.querySelectorAll("#sf-saved li").length;
          document.getElementById("sf-wishlist-count").textContent = left;
          document.getElementById("sf-empty").hidden = left > 0;
        });
      }
    </script>`, wishlist.length);

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (req.method === "GET" && url.pathname === "/") return send(res, 200, "text/html; charset=utf-8", listPage());
    if (req.method === "GET" && url.pathname === "/wishlist") return send(res, 200, "text/html; charset=utf-8", wishlistPage());
    const detail = url.pathname.match(/^\/products\/(\d+)$/);
    if (req.method === "GET" && detail) {
      const id = Number(detail[1]);
      const product = PRODUCTS.find((p) => p.id === id);
      if (!product) return send(res, 404, "text/html; charset=utf-8", notFoundPage());
      return send(res, 200, "text/html; charset=utf-8", detailPage(product));
    }
    if (url.pathname === "/api/wishlist" && req.method === "GET") return json(res, 200, { ids: wishlist });
    if (url.pathname === "/api/wishlist" && req.method === "POST") {
      let raw = "";
      for await (const chunk of req) raw += chunk;
      const id = Number(JSON.parse(raw || "{}").id);
      if (!PRODUCTS.some((p) => p.id === id)) return json(res, 404, { error: "Unknown product" });
      const added = !wishlist.includes(id);
      if (added) wishlist.push(id);
      return json(res, 200, { added, count: wishlist.length });
    }
    const removal = url.pathname.match(/^\/api\/wishlist\/(\d+)$/);
    if (removal && req.method === "DELETE") {
      const removedId = Number(removal[1]);
      wishlist = wishlist.filter((id) => id !== removedId);
      return json(res, 200, { count: wishlist.length });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      wishlist = [];
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
