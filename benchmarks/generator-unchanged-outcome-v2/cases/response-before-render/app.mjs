// Apache-2.0.
import { createServer } from 'node:http';
const PORT = __PORT__;
const RESPONSE_DELAY = 0;
const RENDER_DELAY = 700;
const page = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Minimum controls</title></head><body>
<main><h1>Minimum controls</h1>
<section aria-label="Async control"><h2>Async control</h2><p role="status" aria-label="Async value">1</p><button type="button">Async fewer</button><p role="status" aria-label="Completion">Ready</p></section>
<section aria-label="Sync control"><h2>Sync control</h2><p role="status" aria-label="Sync value">1</p><button type="button">Sync fewer</button></section>
<section aria-label="Disabled control"><h2>Disabled control</h2><p role="status" aria-label="Disabled value">1</p><button type="button" disabled>Disabled fewer</button></section>
</main><script>
const status = name => document.querySelector('[aria-label="' + name + '"]');
const buttons = [...document.querySelectorAll('button')];
let requestId = 0;
buttons[0].addEventListener('click', async () => {
  const id = ++requestId;
  status('Completion').textContent = 'Updating ' + id;
  const response = await fetch('/api/fewer', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({id})});
  const data = await response.json();
  setTimeout(() => {
    status('Async value').textContent = String(data.value);
    status('Completion').textContent = 'Update ' + id + ' complete';
    console.log('UNCHANGED_COMMIT ' + JSON.stringify({id, value: status('Async value').textContent}));
  }, ${RENDER_DELAY});
});
buttons[1].addEventListener('click', () => { status('Sync value').textContent = String(Math.max(1, Number(status('Sync value').textContent) - 1)); });
</script></body></html>`;
createServer(async (req, res) => {
  const send = (code, type, body) => {res.writeHead(code, {'content-type':type, 'cache-control':'no-store'}); res.end(body);};
  if(req.url === '/health') return send(200,'text/plain','ok');
  if(req.url === '/' && req.method === 'GET') return send(200,'text/html',page);
  if(req.url === '/api/fewer' && req.method === 'POST') {
    let raw = ''; for await (const part of req) raw += part;
    const {id} = JSON.parse(raw);
    return setTimeout(() => send(200,'application/json',JSON.stringify({id,value:1})), RESPONSE_DELAY);
  }
  send(404,'text/plain','not found');
}).listen(PORT,'127.0.0.1');
