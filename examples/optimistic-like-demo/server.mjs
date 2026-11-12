import { createServer as createHttpServer } from "node:http";
import { fileURLToPath } from "node:url";
import { createServer as createViteServer } from "vite";

const host = "127.0.0.1";
const port = Number(process.env.PORT ?? "4173");
let liked = false;
let failNextLike = false;

const vite = await createViteServer({
  configFile: fileURLToPath(new URL("./vite.config.mjs", import.meta.url)),
  appType: "spa",
  server: { middlewareMode: true, hmr: false },
});

function sendJson(res, status, body) {
  res.writeHead(status, { "cache-control": "no-store", "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

createHttpServer(async (req, res) => {
  const { pathname } = new URL(req.url ?? "/", `http://${host}:${port}`);
  if (req.method === "GET" && pathname === "/api/health") return sendJson(res, 200, { ok: true });
  if (req.method === "GET" && pathname === "/api/like") return sendJson(res, 200, { liked });
  if (req.method === "POST" && pathname === "/api/reset") {
    liked = false;
    failNextLike = false;
    res.writeHead(204);
    return res.end();
  }
  if (req.method === "POST" && pathname === "/api/fail-next") {
    failNextLike = true;
    return sendJson(res, 200, { armed: true });
  }
  if (req.method === "POST" && pathname === "/api/like") {
    if (failNextLike) {
      failNextLike = false;
      return sendJson(res, 500, { error: "Could not save like" });
    }
    liked = true;
    return sendJson(res, 200, { liked });
  }
  vite.middlewares(req, res, () => sendJson(res, 404, { error: "not found" }));
}).listen(port, host, () => console.log(`Like demo: http://${host}:${port}`));
