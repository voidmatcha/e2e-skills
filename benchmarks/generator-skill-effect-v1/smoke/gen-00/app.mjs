import { createServer } from "node:http";

const PORT = __PORT__;

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Tip calculator</title></head>
<body>
  <main>
    <h1>Tip calculator</h1>
    <form id="tc-form">
      <label for="tc-amount">Bill amount</label>
      <input id="tc-amount" name="amount" inputmode="decimal" autocomplete="off">
      <label for="tc-percent">Tip percentage</label>
      <select id="tc-percent" name="percent">
        <option value="10">10%</option>
        <option value="15" selected>15%</option>
        <option value="20">20%</option>
      </select>
    </form>
    <p id="tc-error" role="alert"></p>
    <p id="tc-tip" aria-live="polite"></p>
    <p id="tc-total" aria-live="polite"></p>
  </main>
  <script>
    const amountEl = document.getElementById("tc-amount");
    const percentEl = document.getElementById("tc-percent");
    const errorEl = document.getElementById("tc-error");
    const tipEl = document.getElementById("tc-tip");
    const totalEl = document.getElementById("tc-total");
    const money = (n) => "$" + n.toFixed(2);

    function update() {
      const amount = Number(amountEl.value);
      if (amountEl.value.trim() === "" ) { errorEl.textContent = ""; tipEl.textContent = ""; totalEl.textContent = ""; return; }
      if (!Number.isFinite(amount) || amount <= 0) {
        errorEl.textContent = "Enter a positive amount";
        tipEl.textContent = "";
        totalEl.textContent = "";
        return;
      }
      errorEl.textContent = "";
      const tip = (amount * Number(percentEl.value)) / 100;
      tipEl.textContent = "Tip: " + money(tip);
      totalEl.textContent = "Total: " + money(amount + tip);
    }
    amountEl.addEventListener("input", update);
    percentEl.addEventListener("change", update);
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/") return send(res, 200, "text/html; charset=utf-8", page);
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
