import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => ({
  repeat: false,
  tracks: [
    { id: 1, title: "Blue in Green", seconds: 337 },
    { id: 2, title: "So What", seconds: 562 },
    { id: 3, title: "Freddie Freeloader", seconds: 589 },
    { id: 4, title: "All Blues", seconds: 693 },
  ],
});
let state = seed();

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
<head><meta charset="utf-8"><title>Playlist</title></head>
<body>
  <main>
    <h1>Playlist</h1>
    <div id="pl-toolbar" class="toolbar">
      <button type="button" id="pl-repeat" aria-pressed="false">Repeat</button>
      <span id="pl-total" class="total">Total 0:00</span>
    </div>
    <div id="pl-now" class="now-playing" hidden>
      <span class="now-label">Now playing:</span> <span id="pl-now-title" class="now-title"></span>
      <button type="button" id="pl-stop">Stop</button>
    </div>
    <ol id="pl-tracks" class="tracks" aria-label="Tracks"></ol>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let data = { repeat: false, tracks: [] };
    let playing = null;
    const clock = (s) => Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function render() {
      el("pl-tracks").replaceChildren(...data.tracks.map((track, index) => {
        const li = document.createElement("li");
        li.className = playing === track.id ? "track playing" : "track";
        const title = document.createElement("span");
        title.className = "title";
        title.textContent = track.title;
        const length = document.createElement("span");
        length.className = "length";
        length.textContent = clock(track.seconds);
        const play = document.createElement("button");
        play.type = "button";
        play.textContent = "Play";
        play.setAttribute("aria-label", "Play " + track.title);
        play.addEventListener("click", () => { playing = track.id; render(); });
        const up = document.createElement("button");
        up.type = "button";
        up.textContent = "Move up";
        up.setAttribute("aria-label", "Move " + track.title + " up");
        up.disabled = index === 0;
        up.addEventListener("click", () => move(index, index - 1));
        const down = document.createElement("button");
        down.type = "button";
        down.textContent = "Move down";
        down.setAttribute("aria-label", "Move " + track.title + " down");
        down.disabled = index === data.tracks.length - 1;
        down.addEventListener("click", () => move(index, index + 1));
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Remove";
        remove.setAttribute("aria-label", "Remove " + track.title);
        remove.addEventListener("click", async () => {
          const next = await api("DELETE", "/api/tracks/" + track.id);
          if (!next) return;
          data = next;
          if (playing === track.id) playing = null;
          render();
        });
        li.append(title, length, play, up, down, remove);
        return li;
      }));
      const total = data.tracks.reduce((sum, t) => sum + t.seconds, 0);
      el("pl-total").textContent = "Total " + clock(total);
      const current = data.tracks.find((t) => t.id === playing);
      el("pl-now").hidden = !current;
      el("pl-now-title").textContent = current ? current.title : "";
      el("pl-repeat").setAttribute("aria-pressed", String(data.repeat));
    }

    async function move(from, to) {
      const order = data.tracks.map((t) => t.id);
      [order[from], order[to]] = [order[to], order[from]];
      const next = await api("PUT", "/api/order", { order });
      if (!next) return;
      data = next;
      render();
    }

    el("pl-stop").addEventListener("click", () => { playing = null; render(); });
    el("pl-repeat").addEventListener("click", async () => {
      const next = await api("PATCH", "/api/repeat", { repeat: !data.repeat });
      if (!next) return;
      data = next;
      render();
    });

    api("GET", "/api/playlist").then((d) => { data = d; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/playlist" && req.method === "GET") return json(res, 200, state);
    if (url.pathname === "/api/order" && req.method === "PUT") {
      const { order = [] } = await readJson(req);
      if (order.length !== state.tracks.length || order.some((id) => !state.tracks.some((t) => t.id === id))) return json(res, 400, { error: "Bad order" });
      state.tracks = order.map((id) => state.tracks.find((t) => t.id === id));
      return json(res, 200, state);
    }
    if (url.pathname === "/api/repeat" && req.method === "PATCH") {
      const { repeat } = await readJson(req);
      state.repeat = Boolean(repeat);
      return json(res, 200, state);
    }
    const match = url.pathname.match(/^\/api\/tracks\/(\d+)$/);
    if (match && req.method === "DELETE") {
      const removedId = Number(match[1]);
      state.tracks = state.tracks.filter((t) => t.id !== removedId);
      return json(res, 200, state);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      state = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
