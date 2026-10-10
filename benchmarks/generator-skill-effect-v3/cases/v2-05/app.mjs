import { createServer } from "node:http";
import { randomBytes } from "node:crypto";

const PORT = __PORT__;
const DATES = ["Mon 12", "Tue 13", "Wed 14"];
const TIMES = ["09:00", "10:00", "11:00"];
let bookings = [];
let nextId = 1;

const send = (res, status, type, body, headers = {}) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store", ...headers });
  res.end(body);
};
const json = (res, status, body, headers) => send(res, status, "application/json", JSON.stringify(body), headers);
const readJson = async (req) => {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
};
const guestOf = (req) => {
  const match = /(?:^|;\s*)guest=([a-f0-9]+)/.exec(req.headers.cookie || "");
  return match ? match[1] : null;
};
const stateFor = (guest) => ({
  dates: DATES,
  slots: DATES.flatMap((date) => TIMES.map((time) => {
    const booking = bookings.find((b) => b.date === date && b.time === time);
    return { date, time, taken: Boolean(booking), mine: Boolean(booking && booking.by === guest), id: booking && booking.by === guest ? booking.id : null };
  })),
  mine: bookings.filter((b) => b.by === guest).map(({ id, date, time }) => ({ id, date, time })),
});

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Appointments</title></head>
<body>
  <main>
    <h1>Appointments</h1>
    <div id="bk-days" role="tablist" aria-label="Days"></div>
    <p id="bk-message" role="alert"></p>
    <ul id="bk-slots" aria-label="Slots"></ul>
    <section id="bk-mine-section">
      <h2 id="bk-mine-heading">My bookings (0)</h2>
      <ul id="bk-mine" aria-label="My bookings"></ul>
    </section>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let state = null;
    let day = null;

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return { ok: res.ok, status: res.status, body: await res.json() };
    }

    function renderDays() {
      el("bk-days").replaceChildren(...state.dates.map((date) => {
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("role", "tab");
        button.setAttribute("aria-selected", String(date === day));
        button.textContent = date;
        button.addEventListener("click", () => { day = date; render(); });
        return button;
      }));
    }

    function renderSlots() {
      el("bk-slots").replaceChildren(...state.slots.filter((slot) => slot.date === day).map((slot) => {
        const li = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = slot.time + (slot.taken ? (slot.mine ? " — Yours" : " — Taken") : "");
        li.append(label);
        if (!slot.taken) {
          const book = document.createElement("button");
          book.type = "button";
          book.textContent = "Book";
          book.setAttribute("aria-label", "Book " + slot.time + " on " + slot.date);
          book.addEventListener("click", () => bookSlot(slot));
          li.append(book);
        }
        return li;
      }));
    }

    function renderMine() {
      el("bk-mine-heading").textContent = "My bookings (" + state.mine.length + ")";
      el("bk-mine").replaceChildren(...state.mine.map((booking) => {
        const li = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = booking.date + " " + booking.time;
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.textContent = "Cancel";
        cancel.setAttribute("aria-label", "Cancel " + booking.date + " " + booking.time);
        cancel.addEventListener("click", async () => {
          await api("DELETE", "/api/bookings/" + booking.id);
          state.mine = state.mine.filter((b) => b.id !== booking.id);
          const slot = state.slots.find((s) => s.date === booking.date && s.time === booking.time);
          slot.taken = false;
          slot.mine = false;
          render();
        });
        li.append(label, cancel);
        return li;
      }));
    }

    function render() {
      renderDays();
      renderSlots();
      renderMine();
    }

    async function refresh() {
      state = (await api("GET", "/api/state")).body;
      if (!day) day = state.dates[0];
      render();
    }

    async function bookSlot(slot) {
      el("bk-message").textContent = "";
      const result = await api("POST", "/api/bookings", { date: slot.date, time: slot.time });
      if (result.status === 409) {
        el("bk-message").textContent = result.body.error;
        await refresh();
        return;
      }
      if (!result.ok) return;
      state.mine.push(result.body);
      slot.taken = true;
      slot.mine = true;
      slot.id = result.body.id;
      render();
    }

    refresh();
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    let guest = guestOf(req);
    const headers = {};
    if (!guest) {
      guest = randomBytes(8).toString("hex");
      headers["set-cookie"] = "guest=" + guest + "; Path=/";
    }
    if (url.pathname === "/api/state" && req.method === "GET") return json(res, 200, stateFor(guest), headers);
    if (url.pathname === "/api/bookings" && req.method === "POST") {
      const { date, time } = await readJson(req);
      if (!DATES.includes(date) || !TIMES.includes(time)) return json(res, 400, { error: "Unknown slot" }, headers);
      if (bookings.some((b) => b.date === date && b.time === time)) return json(res, 409, { error: "That slot was just taken" }, headers);
      const booking = { id: nextId++, date, time, by: guest };
      bookings.push(booking);
      return json(res, 201, { id: booking.id, date, time }, headers);
    }
    const match = url.pathname.match(/^\/api\/bookings\/(\d+)$/);
    if (match && req.method === "DELETE") {
      const id = Number(match[1]);
      bookings = bookings.filter((b) => !(b.id === id && b.by === guest));
      return json(res, 200, { ok: true }, headers);
    }
    if (url.pathname === "/api/dev/take" && req.method === "POST") {
      const { date, time } = await readJson(req);
      if (!bookings.some((b) => b.date === date && b.time === time)) bookings.push({ id: nextId++, date, time, by: "someone-else" });
      return json(res, 201, { ok: true }, headers);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      bookings = [];
      nextId = 1;
      return json(res, 200, { ok: true }, headers);
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
