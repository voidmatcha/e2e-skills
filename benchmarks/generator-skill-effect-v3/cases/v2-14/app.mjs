import { createServer } from "node:http";

const PORT = __PORT__;
const ITEMS = [
  { name: "Trail map set", price: 50 },
  { name: "Water filter", price: 30 },
];
const SHIPPING = 6;
const COUPONS = {
  SAVE10: { kind: "percent", value: 10 },
  FREESHIP: { kind: "shipping" },
  EXPIRED1: { kind: "percent", value: 20, expired: true },
};
let applied = null;

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
const summary = () => {
  const subtotal = ITEMS.reduce((sum, item) => sum + item.price, 0);
  const coupon = applied ? COUPONS[applied] : null;
  const discount = coupon && coupon.kind === "percent" ? (subtotal * coupon.value) / 100 : 0;
  const shipping = coupon && coupon.kind === "shipping" ? 0 : SHIPPING;
  return { coupon: applied, subtotal, discount, shipping, total: subtotal - discount + shipping };
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Checkout</title></head>
<body>
  <main>
    <h1>Checkout</h1>
    <ul id="cp-items" aria-label="Items">
      ${ITEMS.map((i) => `<li>${i.name} — $${i.price.toFixed(2)}</li>`).join("\n      ")}
    </ul>
    <form id="cp-form">
      <label for="cp-code">Coupon code</label>
      <input id="cp-code" name="code" autocomplete="off">
      <button type="submit">Apply</button>
    </form>
    <p id="cp-error" role="alert"></p>
    <p id="cp-applied" hidden>Applied: <span id="cp-applied-code"></span> <button type="button" id="cp-remove">Remove</button></p>
    <dl id="cp-summary" aria-label="Order summary">
      <dt>Subtotal</dt><dd id="cp-subtotal"></dd>
      <dt>Discount</dt><dd id="cp-discount"></dd>
      <dt>Shipping</dt><dd id="cp-shipping"></dd>
      <dt>Total</dt><dd id="cp-total"></dd>
    </dl>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    const money = (n) => "$" + n.toFixed(2);

    function render(s) {
      el("cp-subtotal").textContent = money(s.subtotal);
      el("cp-discount").textContent = "-" + money(s.discount);
      el("cp-shipping").textContent = money(s.shipping);
      el("cp-total").textContent = money(s.total);
      el("cp-applied").hidden = !s.coupon;
      el("cp-applied-code").textContent = s.coupon || "";
    }

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return { ok: res.ok, body: await res.json() };
    }

    el("cp-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      el("cp-error").textContent = "";
      const result = await api("POST", "/api/coupon", { code: el("cp-code").value.trim() });
      if (!result.ok) {
        el("cp-error").textContent = result.body.error;
        return;
      }
      el("cp-code").value = "";
      render(result.body);
    });
    el("cp-remove").addEventListener("click", async () => {
      const result = await api("DELETE", "/api/coupon");
      render(result.body);
    });

    api("GET", "/api/summary").then((result) => render(result.body));
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/summary" && req.method === "GET") return json(res, 200, summary());
    if (url.pathname === "/api/coupon" && req.method === "POST") {
      const { code = "" } = await readJson(req);
      const key = String(code).trim().toUpperCase();
      const coupon = COUPONS[key];
      if (!coupon) return json(res, 404, { error: "Unknown coupon code" });
      if (coupon.expired) return json(res, 410, { error: "That coupon has expired" });
      applied = key;
      return json(res, 200, summary());
    }
    if (url.pathname === "/api/coupon" && req.method === "DELETE") {
      applied = null;
      return json(res, 200, summary());
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      applied = null;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
