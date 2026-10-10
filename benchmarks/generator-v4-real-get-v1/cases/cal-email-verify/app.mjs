// Apache-2.0. Executes the MIT-licensed Cal.com handler in source/ with dependency doubles.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const PORT = __PORT__;
const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const Module = require("node:module");
let user;
let secondary;
let tokens;

function reset() {
  user = { id: 1, email: "primary@example.test", emailVerified: null, metadata: {}, completedOnboarding: true };
  secondary = { id: 2, email: "secondary@example.test", emailVerified: null };
  tokens = new Map([
    ["primary-token", { id: 10, token: "primary-token", identifier: user.email, expires: new Date(Date.now() + 86400000) }],
    ["secondary-token", { id: 11, token: "secondary-token", identifier: secondary.email, secondaryEmailId: secondary.id, expires: new Date(Date.now() + 86400000) }],
  ]);
}
reset();

const prisma = {
  verificationToken: {
    findFirst: async ({ where }) => tokens.get(where.token) ?? null,
    delete: async ({ where }) => {
      for (const [key, value] of tokens) if (value.id === where.id) tokens.delete(key);
    },
  },
  user: {
    findFirst: async ({ where }) => where.email === user.email ? { ...user } : null,
    findUnique: async ({ where }) => where.email === user.email ? { id: user.id } : null,
    update: async ({ data }) => { Object.assign(user, data); return { ...user }; },
  },
  secondaryEmail: {
    findUnique: async ({ where }) => where.email === secondary.email ? { ...secondary, userId: user.id } : null,
    update: async ({ data }) => { Object.assign(secondary, data); return { ...secondary }; },
  },
};
const dayjs = (value = new Date()) => ({
  value: new Date(value),
  isBefore(other) { return this.value.getTime() < other.value.getTime(); },
});
const doubles = {
  "@calcom/dayjs": dayjs,
  "@calcom/features/onboarding/lib/onboarding-path.service": {
    OnboardingPathService: { getGettingStartedPath: async () => "/getting-started" },
  },
  "@calcom/lib/constants": { IS_STRIPE_ENABLED: false, WEBAPP_URL: "http://127.0.0.1:__PORT__" },
  "@calcom/prisma": { prisma },
  "@calcom/prisma/zod-utils": { userMetadata: { parse: (value) => value } },
  zod: { z: { object: () => ({ parse: (query) => {
    if (typeof query.token !== "string") throw new Error("token required");
    return { token: query.token };
  } }), string: () => ({}) } },
};
const handlerModule = new Module(join(here, "source/verify-email.cjs"));
handlerModule.filename = join(here, "source/verify-email.cjs");
handlerModule.paths = Module._nodeModulePaths(here);
handlerModule.require = (id) => {
  if (!(id in doubles)) throw new Error(`unmocked handler dependency: ${id}`);
  return doubles[id];
};
handlerModule._compile(readFileSync(handlerModule.filename, "utf8"), handlerModule.filename);
const { handler } = handlerModule.exports;

const state = () => ({ primary: Boolean(user.emailVerified), secondary: Boolean(secondary.emailVerified) });
const page = (title, body) => `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${title}</title></head><body><main><h1>${title}</h1>${body}</main></body></html>`;
const summary = () => `<p id="primary-status">Primary: ${state().primary ? "Verified" : "Unverified"}</p><p id="secondary-status">Secondary: ${state().secondary ? "Verified" : "Unverified"}</p>`;
const send = (res, status, type, body) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};
const json = (res, status, data) => send(res, status, "application/json", JSON.stringify(data));

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/health") return send(res, 200, "text/plain", "ok");
  if (url.pathname === "/api/reset" && req.method === "POST") {
    reset();
    return json(res, 200, { ok: true });
  }
  if (url.pathname === "/" && req.method === "GET") {
    return send(res, 200, "text/html", page("Verify email", `${summary()}<a href="/api/auth/verify-email?token=primary-token">Verify primary email</a><a href="/api/auth/verify-email?token=secondary-token">Verify secondary email</a>`));
  }
  if (url.pathname === "/event-types" && req.method === "GET") {
    return send(res, 200, "text/html", page("Event types", summary()));
  }
  if (url.pathname === "/settings/my-account/profile" && req.method === "GET") {
    return send(res, 200, "text/html", page("Account profile", summary()));
  }
  if (url.pathname === "/api/auth/verify-email" && req.method === "GET") {
    const response = {
      status(code) { this.code = code; return this; },
      json(data) { json(res, this.code || 200, data); return this; },
      redirect(target) { res.writeHead(302, { location: target, "cache-control": "no-store" }); res.end(); return this; },
    };
    try { return await handler({ query: Object.fromEntries(url.searchParams) }, response); }
    catch (error) { return json(res, 500, { error: String(error) }); }
  }
  return send(res, 404, "text/plain", "not found");
}).listen(PORT, "127.0.0.1");
