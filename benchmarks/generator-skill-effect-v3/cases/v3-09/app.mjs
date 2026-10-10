import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => [
  { id: "es", name: "Spanish basics", cards: [
    { id: 1, front: "hola", back: "hello", learned: false },
    { id: 2, front: "gracias", back: "thank you", learned: true },
    { id: 3, front: "adiós", back: "goodbye", learned: false },
  ] },
  { id: "caps", name: "Capitals", cards: [
    { id: 4, front: "Norway", back: "Oslo", learned: false },
    { id: 5, front: "Peru", back: "Lima", learned: false },
  ] },
];
let decks = seed();

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
<head><meta charset="utf-8"><title>Flashcards</title></head>
<body>
  <main>
    <h1>Flashcards</h1>
    <div id="fc-decks" class="decks"></div>
    <section id="fc-study" class="study" aria-label="Study" hidden>
      <h2 id="fc-study-title"></h2>
      <p id="fc-progress" class="progress"></p>
      <p id="fc-front" class="card-face"></p>
      <p id="fc-back" class="card-face back" hidden></p>
      <button type="button" id="fc-flip">Flip</button>
      <button type="button" id="fc-got">Got it</button>
      <button type="button" id="fc-again">Again</button>
      <p id="fc-done" class="done" hidden>Session done</p>
      <button type="button" id="fc-close">Back to decks</button>
    </section>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let state = [];
    let session = null;

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function renderDecks() {
      el("fc-decks").replaceChildren(...state.map((deck) => {
        const article = document.createElement("article");
        article.className = "deck";
        const heading = document.createElement("h2");
        heading.textContent = deck.name;
        const line = document.createElement("p");
        line.className = "deck-line";
        const learned = deck.cards.filter((c) => c.learned).length;
        line.textContent = deck.cards.length + " cards · " + learned + " learned";
        const study = document.createElement("button");
        study.type = "button";
        study.textContent = "Study";
        study.setAttribute("aria-label", "Study " + deck.name);
        study.addEventListener("click", () => { session = { deckId: deck.id, index: 0, flipped: false, done: false }; render(); });
        article.append(heading, line, study);
        return article;
      }));
    }

    function renderStudy() {
      const panel = el("fc-study");
      panel.hidden = !session;
      if (!session) return;
      const deck = state.find((d) => d.id === session.deckId);
      el("fc-study-title").textContent = "Studying " + deck.name;
      const card = deck.cards[session.index];
      const finished = session.done;
      el("fc-progress").textContent = finished ? "All " + deck.cards.length + " cards reviewed" : "Card " + (session.index + 1) + " of " + deck.cards.length;
      el("fc-front").textContent = finished ? "" : card.front;
      el("fc-back").textContent = finished ? "" : card.back;
      el("fc-back").hidden = finished || !session.flipped;
      el("fc-front").hidden = finished;
      el("fc-flip").hidden = finished;
      el("fc-got").hidden = finished;
      el("fc-again").hidden = finished;
      el("fc-done").hidden = !finished;
    }

    function render() {
      renderDecks();
      renderStudy();
    }

    async function answer(learned) {
      const deck = state.find((d) => d.id === session.deckId);
      const card = deck.cards[session.index];
      const updated = await api("PATCH", "/api/cards/" + card.id, { learned });
      if (!updated) return;
      card.learned = updated.learned;
      if (session.index + 1 >= deck.cards.length) session.done = true;
      else session.index += 1;
      session.flipped = false;
      render();
    }

    el("fc-flip").addEventListener("click", () => { session.flipped = true; render(); });
    el("fc-got").addEventListener("click", () => answer(true));
    el("fc-again").addEventListener("click", () => answer(false));
    el("fc-close").addEventListener("click", () => { session = null; render(); });

    api("GET", "/api/decks").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/decks" && req.method === "GET") return json(res, 200, decks);
    const match = url.pathname.match(/^\/api\/cards\/(\d+)$/);
    if (match && req.method === "PATCH") {
      const card = decks.flatMap((d) => d.cards).find((c) => c.id === Number(match[1]));
      if (!card) return json(res, 404, { error: "Not found" });
      const { learned } = await readJson(req);
      card.learned = Boolean(learned);
      return json(res, 200, card);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      decks = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
