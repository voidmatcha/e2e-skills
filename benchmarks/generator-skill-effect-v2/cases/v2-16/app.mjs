import { createServer } from "node:http";

const PORT = __PORT__;
const QUESTIONS = [
  { id: "q1", text: "Which planet is the largest?", options: ["Mars", "Jupiter", "Venus"], answer: "Jupiter" },
  { id: "q2", text: "What is the capital of Australia?", options: ["Sydney", "Melbourne", "Canberra"], answer: "Canberra" },
  { id: "q3", text: "What is 2 + 2 × 2?", options: ["6", "8", "4"], answer: "6" },
];
let lastScore = null;

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
<head><meta charset="utf-8"><title>Quiz</title></head>
<body>
  <main>
    <h1>Quick quiz</h1>
    <p id="qz-last" role="status"></p>
    <section id="qz-quiz">
      <p id="qz-progress" aria-live="polite"></p>
      <fieldset id="qz-question">
        <legend id="qz-text"></legend>
        <div id="qz-options"></div>
      </fieldset>
      <button type="button" id="qz-previous">Previous</button>
      <button type="button" id="qz-next">Next</button>
      <button type="button" id="qz-submit" hidden>Submit</button>
    </section>
    <section id="qz-result" hidden>
      <h2 id="qz-score"></h2>
    </section>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let questions = [];
    let index = 0;
    const answers = {};

    function render() {
      const q = questions[index];
      el("qz-progress").textContent = "Question " + (index + 1) + " of " + questions.length;
      el("qz-text").textContent = q.text;
      el("qz-options").replaceChildren(...q.options.map((option, i) => {
        const wrapper = document.createElement("div");
        const input = document.createElement("input");
        input.type = "radio";
        input.name = "answer";
        input.value = option;
        input.id = q.id + "-" + i;
        input.checked = answers[q.id] === option;
        input.addEventListener("change", () => { answers[q.id] = option; refresh(); });
        const label = document.createElement("label");
        label.htmlFor = input.id;
        label.textContent = option;
        wrapper.append(input, label);
        return wrapper;
      }));
      refresh();
    }

    function refresh() {
      const q = questions[index];
      const last = index === questions.length - 1;
      el("qz-previous").disabled = index === 0;
      el("qz-next").hidden = last;
      el("qz-submit").hidden = !last;
      el("qz-next").disabled = !answers[q.id];
      el("qz-submit").disabled = !answers[q.id];
    }

    el("qz-previous").addEventListener("click", () => { index -= 1; render(); });
    el("qz-next").addEventListener("click", () => { index += 1; render(); });
    el("qz-submit").addEventListener("click", async () => {
      const res = await fetch("/api/submissions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ answers }) });
      const body = await res.json();
      el("qz-quiz").hidden = true;
      el("qz-result").hidden = false;
      el("qz-score").textContent = "You scored " + body.score + " of " + body.total;
    });

    fetch("/api/quiz").then((r) => r.json()).then((data) => {
      questions = data.questions;
      if (data.lastScore) el("qz-last").textContent = "Your last score: " + data.lastScore.score + " of " + data.lastScore.total;
      render();
    });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/quiz" && req.method === "GET") {
      return json(res, 200, { questions: QUESTIONS.map(({ id, text, options }) => ({ id, text, options })), lastScore });
    }
    if (url.pathname === "/api/submissions" && req.method === "POST") {
      const { answers = {} } = await readJson(req);
      const score = QUESTIONS.filter((q) => answers[q.id] === q.answer).length;
      lastScore = { score, total: QUESTIONS.length };
      return json(res, 201, lastScore);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      lastScore = null;
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
