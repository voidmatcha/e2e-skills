import { createServer } from "node:http";

const PORT = __PORT__;
const seed = () => [
  { id: 1, text: "How did you hear about us?", type: "single", options: ["Friend", "Search", "Advert"] },
  { id: 2, text: "Which features do you use?", type: "multiple", options: ["Export", "Sharing"] },
];
let questions = seed();

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
<head><meta charset="utf-8"><title>Survey builder</title></head>
<body>
  <main>
    <h1>Survey builder</h1>
    <p id="sb-counter" class="counter">0 questions · 0 options</p>
    <button type="button" id="sb-preview-toggle">Preview</button>
    <div id="sb-questions" class="questions"></div>
    <section id="sb-preview" class="preview" aria-label="Preview" hidden></section>
  </main>
  <script>
    const el = (id) => document.getElementById(id);
    let state = [];
    let previewOpen = false;

    async function api(method, path, body) {
      const res = await fetch(path, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      return res.ok ? res.json() : null;
    }

    function questionCard(q, index) {
      const card = document.createElement("article");
      card.className = "question";
      const heading = document.createElement("h2");
      heading.textContent = "Q" + (index + 1) + ": " + q.text;
      const type = document.createElement("span");
      type.className = "type";
      type.textContent = q.type === "single" ? "single choice" : "multiple choice";
      const options = document.createElement("ul");
      options.setAttribute("aria-label", "Options for " + q.text);
      options.append(...q.options.map((opt, i) => {
        const li = document.createElement("li");
        const label = document.createElement("span");
        label.className = "option-text";
        label.textContent = opt;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Remove option";
        remove.setAttribute("aria-label", "Remove option " + opt + " from " + q.text);
        remove.addEventListener("click", async () => {
          const updated = await api("DELETE", "/api/questions/" + q.id + "/options/" + i);
          if (!updated) return;
          replace(updated);
          render();
        });
        li.append(label, remove);
        return li;
      }));
      const addRow = document.createElement("div");
      addRow.className = "add-option";
      const labelId = "sb-add-label-" + q.id;
      const labelSpan = document.createElement("span");
      labelSpan.id = labelId;
      labelSpan.className = "field-label";
      labelSpan.textContent = "New option for " + q.text;
      const input = document.createElement("input");
      input.setAttribute("aria-labelledby", labelId);
      input.autocomplete = "off";
      const add = document.createElement("button");
      add.type = "button";
      add.textContent = "Add option";
      add.setAttribute("aria-label", "Add option to " + q.text);
      add.addEventListener("click", async () => {
        const text = input.value.trim();
        if (!text) return;
        const updated = await api("POST", "/api/questions/" + q.id + "/options", { text });
        if (!updated) return;
        replace(updated);
        render();
      });
      addRow.append(labelSpan, input, add);
      const up = document.createElement("button");
      up.type = "button";
      up.textContent = "Move question up";
      up.setAttribute("aria-label", "Move question up: " + q.text);
      up.disabled = index === 0;
      up.addEventListener("click", () => move(index, index - 1));
      const down = document.createElement("button");
      down.type = "button";
      down.textContent = "Move question down";
      down.setAttribute("aria-label", "Move question down: " + q.text);
      down.disabled = index === state.length - 1;
      down.addEventListener("click", () => move(index, index + 1));
      card.append(heading, type, options, addRow, up, down);
      return card;
    }

    function replace(updated) {
      state = state.map((q) => (q.id === updated.id ? updated : q));
    }

    async function move(from, to) {
      const order = state.map((q) => q.id);
      [order[from], order[to]] = [order[to], order[from]];
      const next = await api("PUT", "/api/order", { order });
      if (!next) return;
      state = next;
      render();
    }

    function renderPreview() {
      const preview = el("sb-preview");
      preview.hidden = !previewOpen;
      preview.replaceChildren(...state.map((q, index) => {
        const fieldset = document.createElement("fieldset");
        const legend = document.createElement("legend");
        legend.textContent = (index + 1) + ". " + q.text;
        fieldset.append(legend);
        for (const opt of q.options) {
          const wrapper = document.createElement("div");
          const input = document.createElement("input");
          input.type = q.type === "single" ? "radio" : "checkbox";
          input.name = "q" + q.id;
          input.id = "pv-" + q.id + "-" + opt.replace(/\\W/g, "").toLowerCase();
          const label = document.createElement("label");
          label.htmlFor = input.id;
          label.textContent = opt;
          wrapper.append(input, label);
          fieldset.append(wrapper);
        }
        return fieldset;
      }));
    }

    function render() {
      el("sb-questions").replaceChildren(...state.map(questionCard));
      const options = state.reduce((sum, q) => sum + q.options.length, 0);
      el("sb-counter").textContent = state.length + (state.length === 1 ? " question" : " questions") + " · " + options + (options === 1 ? " option" : " options");
      el("sb-preview-toggle").textContent = previewOpen ? "Hide preview" : "Preview";
      renderPreview();
    }

    el("sb-preview-toggle").addEventListener("click", () => { previewOpen = !previewOpen; render(); });
    api("GET", "/api/questions").then((list) => { state = list; render(); });
  </script>
</body>
</html>`;

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
    if (url.pathname === "/" && req.method === "GET") return send(res, 200, "text/html; charset=utf-8", page);
    if (url.pathname === "/api/questions" && req.method === "GET") return json(res, 200, questions);
    if (url.pathname === "/api/order" && req.method === "PUT") {
      const { order = [] } = await readJson(req);
      if (order.length !== questions.length || order.some((id) => !questions.some((q) => q.id === id))) return json(res, 400, { error: "Bad order" });
      questions = order.map((id) => questions.find((q) => q.id === id));
      return json(res, 200, questions);
    }
    const add = url.pathname.match(/^\/api\/questions\/(\d+)\/options$/);
    if (add && req.method === "POST") {
      const question = questions.find((q) => q.id === Number(add[1]));
      if (!question) return json(res, 404, { error: "Not found" });
      const { text = "" } = await readJson(req);
      if (!String(text).trim()) return json(res, 400, { error: "Text is required" });
      question.options.push(String(text).trim());
      return json(res, 200, question);
    }
    const del = url.pathname.match(/^\/api\/questions\/(\d+)\/options\/(\d+)$/);
    if (del && req.method === "DELETE") {
      const question = questions.find((q) => q.id === Number(del[1]));
      if (!question) return json(res, 404, { error: "Not found" });
      const index = Number(del[2]);
      if (index >= 0 && index < question.options.length) question.options.splice(index, 1);
      return json(res, 200, question);
    }
    if (url.pathname === "/api/reset" && req.method === "POST") {
      questions = seed();
      return json(res, 200, { ok: true });
    }
    return send(res, 404, "text/plain", "not found");
  } catch (error) {
    return json(res, 500, { error: "internal error" });
  }
}).listen(PORT, "127.0.0.1");
