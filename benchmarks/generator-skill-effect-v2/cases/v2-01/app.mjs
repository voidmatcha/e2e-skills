import { createServer } from "node:http";

const PORT = __PORT__;
const CART = [
  { name: "Desk lamp", price: 40 },
  { name: "Notebook", price: 8 },
];
const METHODS = { standard: { label: "Standard", cost: 5 }, express: { label: "Express", cost: 15 } };
let orders = [];
let nextNumber = 1001;

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
<head><meta charset="utf-8"><title>Checkout</title></head>
<body>
  <main>
    <h1>Checkout</h1>
    <p id="co-step" aria-live="polite"></p>
    <section id="co-shipping">
      <h2>Shipping address</h2>
      <form id="co-address-form">
        <label for="co-name">Full name</label>
        <input id="co-name" name="name" autocomplete="off">
        <label for="co-street">Street</label>
        <input id="co-street" name="street" autocomplete="off">
        <label for="co-city">City</label>
        <input id="co-city" name="city" autocomplete="off">
        <button type="submit">Next</button>
      </form>
    </section>
    <section id="co-method" hidden>
      <h2>Shipping method</h2>
      <fieldset id="co-methods">
        <legend>Choose a method</legend>
        <div><input type="radio" id="co-standard" name="method" value="standard" checked><label for="co-standard">Standard ($5.00)</label></div>
        <div><input type="radio" id="co-express" name="method" value="express"><label for="co-express">Express ($15.00)</label></div>
      </fieldset>
      <button type="button" id="co-method-back">Back</button>
      <button type="button" id="co-method-next">Next</button>
    </section>
    <section id="co-review" hidden>
      <h2>Review</h2>
      <ul id="co-items" aria-label="Items"></ul>
      <p id="co-shipping-line"></p>
      <p id="co-total"></p>
      <p id="co-error" role="alert"></p>
      <button type="button" id="co-review-back">Back</button>
      <button type="button" id="co-confirm">Confirm order</button>
    </section>
    <section id="co-done" hidden>
      <h2>Thank you</h2>
      <p id="co-confirmation" role="status"></p>
    </section>
    <section id="co-history">
      <h2>Your orders</h2>
      <ul id="co-orders" aria-label="Your orders"></ul>
    </section>
  </main>
  <script>
    const cart = ${JSON.stringify(CART)};
    const methods = ${JSON.stringify(METHODS)};
    const money = (n) => "$" + n.toFixed(2);
    const el = (id) => document.getElementById(id);
    const sections = { shipping: el("co-shipping"), method: el("co-method"), review: el("co-review"), done: el("co-done") };
    const state = { step: "shipping", address: null, method: "standard" };

    function show(step) {
      state.step = step;
      for (const [name, section] of Object.entries(sections)) section.hidden = name !== step;
      el("co-step").textContent = { shipping: "Step 1 of 3", method: "Step 2 of 3", review: "Step 3 of 3", done: "Order placed" }[step];
      if (step === "shipping" && state.address) {
        el("co-name").value = state.address.name;
        el("co-street").value = state.address.street;
        el("co-city").value = state.address.city;
      }
      if (step === "review") renderReview();
    }

    function renderReview() {
      const items = el("co-items");
      items.replaceChildren(...cart.map((item) => {
        const li = document.createElement("li");
        li.textContent = item.name + " — " + money(item.price);
        return li;
      }));
      const subtotal = cart.reduce((sum, item) => sum + item.price, 0);
      const shipping = methods[state.method];
      el("co-shipping-line").textContent = "Shipping (" + shipping.label + "): " + money(shipping.cost);
      el("co-total").textContent = "Total: " + money(subtotal + shipping.cost);
      el("co-error").textContent = "";
    }

    async function loadOrders() {
      const list = await (await fetch("/api/orders")).json();
      el("co-orders").replaceChildren(...list.map((order) => {
        const li = document.createElement("li");
        li.textContent = "Order #" + order.number + " — " + money(order.total) + " — " + order.city;
        return li;
      }));
    }

    el("co-address-form").addEventListener("submit", (event) => {
      event.preventDefault();
      state.address = { name: el("co-name").value, street: el("co-street").value, city: el("co-city").value };
      event.target.reset();
      show("method");
    });
    el("co-method-back").addEventListener("click", () => show("shipping"));
    el("co-method-next").addEventListener("click", () => {
      state.method = document.querySelector("input[name=method]:checked").value;
      show("review");
    });
    el("co-review-back").addEventListener("click", () => show("method"));
    el("co-confirm").addEventListener("click", async () => {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ address: state.address, method: state.method }),
      });
      const body = await res.json();
      if (!res.ok) {
        el("co-error").textContent = body.error;
        return;
      }
      el("co-confirmation").textContent = "Order #" + body.number + " confirmed";
      show("done");
      loadOrders();
    });

    show("shipping");
    loadOrders();
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/orders" && req.method === "GET") return json(res, 200, orders);
    if (url.pathname === "/api/orders" && req.method === "POST") {
      const { address = {}, method = "standard" } = await readJson(req);
      const shipping = METHODS[method] || METHODS.standard;
      const total = CART.reduce((sum, item) => sum + item.price, 0) + shipping.cost;
      const order = { number: nextNumber, city: String(address.city || ""), method, total };
      if (order.city === "Failville") {
        return json(res, 402, { error: "Payment declined" });
      }
      nextNumber += 1;
      orders.push(order);
      return json(res, 201, order);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      orders = [];
      nextNumber = 1001;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
