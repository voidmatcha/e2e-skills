import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1]);
}

const rootArgument = args.get("--root");
const requestedPort = Number.parseInt(args.get("--port") ?? "0", 10);
if (!rootArgument || !Number.isInteger(requestedPort) || requestedPort < 0) {
  throw new Error("usage: node server.mjs --root <directory> --port <port>");
}
const root = resolve(rootArgument);

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
]);

const server = createServer(async (request, response) => {
  const pathname = new URL(request.url ?? "/", "http://fixture.local").pathname;
  const relativePath = pathname === "/" ? "index.html" : pathname.slice(1);
  const filePath = resolve(root, relativePath);

  if (filePath !== root && !filePath.startsWith(`${root}${sep}`)) {
    response.writeHead(403).end("Forbidden");
    return;
  }

  try {
    const metadata = await stat(filePath);
    if (!metadata.isFile()) {
      throw new Error("not a file");
    }
    response.writeHead(200, {
      "Cache-Control": "no-store",
      "Content-Type": contentTypes.get(extname(filePath)) ?? "application/octet-stream",
    });
    createReadStream(filePath).pipe(response);
  } catch {
    response.writeHead(404).end("Not found");
  }
});

server.listen(requestedPort, "127.0.0.1", () => {
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("server did not bind a TCP port");
  }
  process.stdout.write(`${JSON.stringify({ port: address.port })}\n`);
});

const stop = () => server.close(() => process.exit(0));
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
