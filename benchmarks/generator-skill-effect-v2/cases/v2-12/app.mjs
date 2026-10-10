import { createServer } from "node:http";

const PORT = __PORT__;
let expenses = [];
let nextId = 1;

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
const validAmount = (value) => Number.isFinite(Number(value)) && Number(value) > 0;

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Expenses</title></head>
<body>
  <main>
    <h1>Expenses</h1>
    <p id="ex-total" aria-live="polite">Total: $0.00</p>
    <form id="ex-form" novalidate>
      <label for="ex-description">Description</label>
      <input id="ex-description" name="description" autocomplete="off">
      <label for="ex-amount">Amount</label>
      <input id="ex-amount" name="amount" autocomplete="off" inputmode="decimal" aria-describedby="ex-amount-error">
      <span id="ex-amount-error" role="alert"></span>
      <button type="submit">Add</button>
    </form>
    <ul id="ex-list" aria-label="Expenses"></ul>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    const money = (n) => "$" + Number(n).toFixed(2);
    const validAmount = (value) => Number.isFinite(Number(value)) && String(value).trim() !== "" && Number(value) > 0;
    let state = [];
    let editing = null;

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function showAmountError() {
      el("ex-amount-error").textContent = validAmount(el("ex-amount").value) ? "" : "Amount must be a positive number";
    }

    function row(expense) {
      const li = document.createElement("li");
      li.className = "expense";
      const description = document.createElement("span");
      description.textContent = expense.description;
      li.append(description);
      if (editing === expense.id) {
        const input = document.createElement("input");
        input.value = expense.amount;
        input.setAttribute("aria-label", "New amount for " + expense.description);
        const save = document.createElement("button");
        save.type = "button";
        save.textContent = "Save";
        save.setAttribute("aria-label", "Save " + expense.description);
        save.addEventListener("click", async () => {
          if (!validAmount(input.value)) return;
          const amount = Number(input.value);
          await api("PATCH", "/api/expenses/" + expense.id, { amount });
          expense.amount = amount;
          editing = null;
          render();
        });
        li.append(" ", input, save);
      } else {
        const amount = document.createElement("span");
        amount.className = "amount";
        amount.textContent = " " + money(expense.amount);
        const edit = document.createElement("button");
        edit.type = "button";
        edit.textContent = "Edit";
        edit.setAttribute("aria-label", "Edit " + expense.description);
        edit.addEventListener("click", () => { editing = expense.id; render(); });
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Delete";
        remove.setAttribute("aria-label", "Delete " + expense.description);
        remove.addEventListener("click", async () => {
          await api("DELETE", "/api/expenses/" + expense.id);
          state = state.filter((e) => e.id !== expense.id);
          render();
        });
        li.append(amount, edit, remove);
      }
      return li;
    }

    function render() {
      const ordered = [...state].sort((a, b) => b.id - a.id);
      el("ex-list").replaceChildren(...ordered.map(row));
      el("ex-total").textContent = "Total: " + money(state.reduce((sum, e) => sum + e.amount, 0));
    }

    el("ex-amount").addEventListener("blur", showAmountError);
    el("ex-amount").addEventListener("input", () => { if (validAmount(el("ex-amount").value)) el("ex-amount-error").textContent = ""; });
    el("ex-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      showAmountError();
      if (!validAmount(el("ex-amount").value)) return;
      const payload = { description: el("ex-description").value, amount: Number(el("ex-amount").value) };
      for (const field of el("ex-form").elements) field.disabled = true;
      const created = await api("POST", "/api/expenses", payload);
      for (const field of el("ex-form").elements) field.disabled = false;
      if (!created) return;
      state.push(created);
      el("ex-form").reset();
      render();
    });

    api("GET", "/api/expenses").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/expenses" && req.method === "GET") return json(res, 200, expenses);
    if (url.pathname === "/api/expenses" && req.method === "POST") {
      const { description = "", amount } = await readJson(req);
      if (!String(description).trim()) return json(res, 400, { error: "Description is required" });
      if (!validAmount(amount)) return json(res, 400, { error: "Amount must be a positive number" });
      const expense = { id: nextId++, description: String(description).trim(), amount: Number(amount) };
      expenses.push(expense);
      return json(res, 201, expense);
    }
    const match = url.pathname.match(/^\/api\/expenses\/(\d+)$/);
    if (match && req.method === "PATCH") {
      const expense = expenses.find((e) => e.id === Number(match[1]));
      if (!expense) return json(res, 404, { error: "Not found" });
      const { amount } = await readJson(req);
      if (!validAmount(amount)) return json(res, 400, { error: "Amount must be a positive number" });
      expense.amount = Number(amount);
      return json(res, 200, expense);
    }
    if (match && req.method === "DELETE") {
      const removedId = Number(match[1]);
      expenses = expenses.filter((e) => e.id !== removedId);
      return json(res, 200, { ok: true });
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      expenses = [];
      nextId = 1;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
