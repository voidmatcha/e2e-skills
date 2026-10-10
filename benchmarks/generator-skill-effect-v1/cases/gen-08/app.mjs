import { createServer } from "node:http";
import { randomBytes } from "node:crypto";

const PORT = __PORT__;
const OPTIONS = ["Vim", "Emacs", "VS Code"];
let votes = Object.fromEntries(OPTIONS.map((o) => [o, 0]));
let voted = new Set();

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
const visitorId = (req) => {
  const match = /(?:^|;\s*)visitor=([a-f0-9]+)/.exec(req.headers.cookie || "");
  return match ? match[1] : null;
};
const summary = (visitor, tally) => ({ options: OPTIONS, votes: tally, voted: voted.has(visitor) });

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Poll</title></head>
<body>
  <main>
    <h1>Which editor do you use?</h1>
    <form id="pl-form">
      <fieldset id="pl-options">
        <legend>Pick one</legend>
      </fieldset>
      <button type="button" id="pl-vote">Vote</button>
    </form>
    <p id="pl-status" role="status"></p>
    <section id="pl-results" hidden>
      <h2>Results</h2>
      <ul id="pl-tally" aria-label="Results"></ul>
    </section>
  </main>
  <script>
    const optionsEl = document.getElementById("pl-options");
    const voteEl = document.getElementById("pl-vote");
    const statusEl = document.getElementById("pl-status");
    const resultsEl = document.getElementById("pl-results");
    const tallyEl = document.getElementById("pl-tally");
    let state = null;

    function renderOptions(options) {
      for (const option of options) {
        const wrapper = document.createElement("div");
        wrapper.className = "option";
        const input = document.createElement("input");
        input.type = "radio";
        input.name = "choice";
        input.value = option;
        input.id = "pl-choice-" + option.replace(/\\W/g, "").toLowerCase();
        const label = document.createElement("label");
        label.htmlFor = input.id;
        label.textContent = option;
        wrapper.append(input, label);
        optionsEl.append(wrapper);
      }
    }

    function setDisabled(disabled) {
      for (const input of optionsEl.querySelectorAll("input")) input.disabled = disabled;
      voteEl.disabled = disabled;
    }

    function renderResults(data) {
      const total = Object.values(data.votes).reduce((a, b) => a + b, 0);
      tallyEl.replaceChildren();
      for (const option of data.options) {
        const count = data.votes[option];
        const percent = total === 0 ? 0 : Math.round((100 * count) / total);
        const li = document.createElement("li");
        li.textContent = option + ": " + count + (count === 1 ? " vote" : " votes") + " (" + percent + "%)";
        tallyEl.append(li);
      }
    }

    function show(data) {
      state = data;
      renderResults(data);
      resultsEl.hidden = !data.voted;
      setDisabled(data.voted);
      statusEl.textContent = data.voted ? "Thanks for voting" : "";
    }

    voteEl.addEventListener("click", async () => {
      const choice = optionsEl.querySelector("input:checked");
      if (!choice) {
        statusEl.textContent = "Pick an option first";
        return;
      }
      const res = await fetch("/api/votes", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ option: choice.value }),
      });
      const body = await res.json();
      if (res.ok) show(body);
    });

    fetch("/api/results").then((r) => r.json()).then((data) => { renderOptions(data.options); show(data); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/results" && req.method === "GET") {
      let visitor = visitorId(req);
      const headers = {};
      if (!visitor) {
        visitor = randomBytes(8).toString("hex");
        headers["set-cookie"] = "visitor=" + visitor + "; Path=/";
      }
      return json(res, 200, summary(visitor, votes), headers);
    }
    if (url.pathname === "/api/votes" && req.method === "POST") {
      const visitor = visitorId(req);
      if (!visitor) return json(res, 400, { error: "No visitor cookie" });
      if (voted.has(visitor)) return json(res, 409, { error: "Already voted" });
      const { option } = await readJson(req);
      if (!OPTIONS.includes(option)) return json(res, 400, { error: "Unknown option" });
      const tally = { ...votes, [option]: votes[option] + 1 };
      votes = tally;
      voted.add(visitor);
      return json(res, 201, summary(visitor, tally));
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      votes = Object.fromEntries(OPTIONS.map((o) => [o, 0]));
      voted = new Set();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
