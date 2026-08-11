import { createServer as createHttpServer } from "node:http";
import { fileURLToPath } from "node:url";

import { createServer as createViteServer } from "vite";

const host = "127.0.0.1";
const portText = process.env.PORT ?? "4173";
const port = Number(portText);

if (
  !/^[0-9]+$/.test(portText) ||
  !Number.isSafeInteger(port) ||
  port < 1024 ||
  port > 65_535
) {
  throw new Error("PORT must be an integer between 1024 and 65535");
}

let liked = false;

const vite = await createViteServer({
  configFile: fileURLToPath(new URL("./vite.config.mjs", import.meta.url)),
  appType: "spa",
  server: {
    middlewareMode: true,
    hmr: false,
  },
});

function sendJson(response, status, body) {
  response.writeHead(status, {
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

const server = createHttpServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", `http://${host}:${port}`);

    if (request.method === "GET" && url.pathname === "/api/health") {
      sendJson(response, 200, { ok: true });
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/like") {
      sendJson(response, 200, { liked });
      return;
    }

    if (request.method === "POST" && url.pathname === "/api/reset") {
      liked = false;
      response.writeHead(204, { "cache-control": "no-store" });
      response.end();
      return;
    }

    if (request.method === "POST" && url.pathname === "/api/like") {
      if (request.headers["x-demo-fault"] === "reject") {
        sendJson(response, 503, { error: "demo write rejection" });
        return;
      }

      const body = await readJson(request);
      if (body.liked !== true) {
        sendJson(response, 400, { error: "liked must be true" });
        return;
      }

      liked = true;
      sendJson(response, 200, { liked });
      return;
    }

    vite.middlewares(request, response, (error) => {
      if (error) {
        sendJson(response, 500, { error: "vite middleware failed" });
      }
    });
  } catch {
    if (!response.headersSent) {
      sendJson(response, 500, { error: "request failed" });
    } else {
      response.end();
    }
  }
});

server.listen(port, host, () => {
  console.log(`React optimistic-write example: http://${host}:${port}`);
});

async function shutdown() {
  server.close();
  await vite.close();
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
