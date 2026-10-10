// Apache-2.0
import { createServer } from "node:http";

const PORT = __PORT__;
const SEED = { ruby: 0, blue: 0 };
let counts = { ...SEED };

const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, body) => send(res, status, "application/json", JSON.stringify(body));

const page = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Color poll</title></head>
<body>
  <main>
    <h1>Color poll</h1>
    <p id="vote-total" role="status"></p>
    <ul id="vote-list" aria-label="Poll choices"></ul>
    <p id="vote-error" role="alert" hidden>Vote failed</p>
  </main>
  <script>
    const totalEl = document.getElementById("vote-total");
    const listEl = document.getElementById("vote-list");
    const errorEl = document.getElementById("vote-error");
    const names = { ruby: "Ruby", blue: "Blue" };

    function render(next) {
      totalEl.textContent = "Total votes: " + (next.ruby + next.blue);
      listEl.replaceChildren(...Object.keys(names).map((choice) => {
        const row = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = names[choice] + ": " + next[choice] + " votes";
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Vote " + names[choice];
        button.addEventListener("click", () => vote(choice));
        row.append(label, " ", button);
        return row;
      }));
    }

    async function vote(choice) {
      errorEl.hidden = true;
      const response = await fetch("/api/vote?choice=" + encodeURIComponent(choice));
      if (!response.ok) {
        errorEl.hidden = false;
        return;
      }
      render(await response.json());
    }

    fetch("/api/tally").then((response) => response.json()).then(render);
  </script>
</body>
</html>`;

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
  if (url.pathname === "/api/tally" && req.method === "GET") return json(res, 200, counts);
  if (url.pathname === "/api/vote" && req.method === "GET") {
    const choice = url.searchParams.get("choice");
    if (!(choice in counts)) return json(res, 404, { error: "unknown choice" });
    counts[choice] += 1;
    return json(res, 200, counts);
  }
  if (url.pathname === "/api/reset" && req.method === "POST") {
    counts = { ...SEED };
    return json(res, 200, { ok: true });
  }
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
