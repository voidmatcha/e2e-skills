import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const port = Number(process.env.PORT || 4391);
let todos = [];
let nextId = 1;

function send(res, status, body, type = 'application/json') {
  res.writeHead(status, { 'content-type': type });
  res.end(type === 'application/json' ? JSON.stringify(body) : body);
}

async function readJson(req) {
  let raw = '';
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${port}`);
  if (req.method === 'GET' && url.pathname === '/') {
    return send(res, 200, await readFile(new URL('./public/index.html', import.meta.url)), 'text/html');
  }
  if (req.method === 'GET' && url.pathname === '/api/todos') return send(res, 200, todos);
  if (req.method === 'POST' && url.pathname === '/api/todos') {
    const { title } = await readJson(req);
    if (!title || !title.trim()) return send(res, 400, { error: 'Title is required' });
    if (title.trim().length > 60) return send(res, 400, { error: 'Title must be 60 characters or fewer' });
    const todo = { id: nextId++, title: title.trim(), done: false };
    todos.push(todo);
    return send(res, 201, todo);
  }
  const match = url.pathname.match(/^\/api\/todos\/(\d+)$/);
  if (req.method === 'PATCH' && match) {
    const todo = todos.find((t) => t.id === Number(match[1]));
    if (!todo) return send(res, 404, { error: 'Not found' });
    Object.assign(todo, await readJson(req));
    return send(res, 200, todo);
  }
  if (req.method === 'POST' && url.pathname === '/api/reset') {
    todos = [];
    nextId = 1;
    return send(res, 204, '');
  }
  send(res, 404, { error: 'Not found' });
}).listen(port, () => console.log(`listening on ${port}`));
