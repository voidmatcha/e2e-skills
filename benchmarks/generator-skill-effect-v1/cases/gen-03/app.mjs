import { createServer } from "node:http";

const PORT = __PORT__;

const catalog = [
  { id: "tote", name: "Canvas Tote", price: 25 },
  { id: "beanie", name: "Merino Beanie", price: 30 },
  { id: "mug", name: "Camp Mug", price: 12.5 },
];
let cart = [];

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
<head><meta charset="utf-8"><title>Shop</title></head>
<body>
  <main>
    <h1>Shop</h1>
    <section id="ct-catalog">
      <h2>Catalog</h2>
      <ul id="ct-products" aria-label="Catalog"></ul>
    </section>
    <section id="ct-cart">
      <h2>Cart</h2>
      <p id="ct-empty">Your cart is empty</p>
      <ul id="ct-lines" aria-label="Cart"></ul>
      <p id="ct-total">Total: $0.00</p>
    </section>
  </main>
  <script>
    const catalog = ${JSON.stringify(catalog)};
    const productsEl = document.getElementById("ct-products");
    const linesEl = document.getElementById("ct-lines");
    const totalEl = document.getElementById("ct-total");
    const emptyEl = document.getElementById("ct-empty");
    let state = [];

    const money = (n) => "$" + n.toFixed(2);

    async function api(method, path, body) {
      const res = await fetch(path, {
        method,
        headers: { "content-type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      return res.json();
    }

    function renderCatalog() {
      for (const p of catalog) {
        const li = document.createElement("li");
        li.className = "product";
        const name = document.createElement("span");
        name.textContent = p.name + " — " + money(p.price);
        const add = document.createElement("button");
        add.type = "button";
        add.textContent = "Add to cart";
        add.setAttribute("aria-label", "Add " + p.name + " to cart");
        add.addEventListener("click", async () => {
          const next = await api("POST", "/api/cart/items", { productId: p.id });
          state = next;
          render();
        });
        li.append(name, add);
        productsEl.append(li);
      }
    }

    function render() {
      linesEl.replaceChildren();
      let total = 0;
      for (const line of state) {
        total += line.price * line.quantity;
        const li = document.createElement("li");
        li.className = "line";
        const name = document.createElement("span");
        name.textContent = line.name;
        const qty = document.createElement("span");
        qty.className = "qty";
        qty.textContent = "Qty: " + line.quantity;
        const minus = document.createElement("button");
        minus.type = "button";
        minus.textContent = "−";
        minus.setAttribute("aria-label", "Decrease quantity of " + line.name);
        minus.addEventListener("click", async () => {
          state = await api("PATCH", "/api/cart/items/" + line.id, { quantity: line.quantity - 1 });
          render();
        });
        const plus = document.createElement("button");
        plus.type = "button";
        plus.textContent = "+";
        plus.setAttribute("aria-label", "Increase quantity of " + line.name);
        plus.addEventListener("click", async () => {
          state = await api("PATCH", "/api/cart/items/" + line.id, { quantity: line.quantity + 1 });
          render();
        });
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Remove";
        remove.setAttribute("aria-label", "Remove " + line.name);
        remove.addEventListener("click", async () => {
          await api("DELETE", "/api/cart/items/" + line.id);
          state = state.filter((l) => l.id !== line.id);
          render();
        });
        li.append(name, minus, qty, plus, remove);
        linesEl.append(li);
      }
      totalEl.textContent = "Total: " + money(total);
      emptyEl.hidden = state.length > 0;
    }

    renderCatalog();
    api("GET", "/api/cart").then((cart) => { state = cart; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/cart" && req.method === "GET") return json(res, 200, cart);
    if (url.pathname === "/api/cart/items" && req.method === "POST") {
      const { productId } = await readJson(req);
      const product = catalog.find((p) => p.id === productId);
      if (!product) return json(res, 404, { error: "Unknown product" });
      const existing = cart.find((l) => l.id === product.id);
      if (existing) existing.quantity += 1;
      else cart.push({ id: product.id, name: product.name, price: product.price, quantity: 1 });
      return json(res, 201, cart);
    }
    const match = url.pathname.match(/^\/api\/cart\/items\/([a-z]+)$/);
    if (match && req.method === "PATCH") {
      const line = cart.find((l) => l.id === match[1]);
      if (!line) return json(res, 404, { error: "Not in cart" });
      const { quantity } = await readJson(req);
      line.quantity = Math.max(1, Number(quantity) || 1);
      return json(res, 200, cart);
    }
    if (match && req.method === "DELETE") {
      const removedId = match[1];
      cart = cart.filter((l) => l.id !== removedId);
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      cart = [];
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
