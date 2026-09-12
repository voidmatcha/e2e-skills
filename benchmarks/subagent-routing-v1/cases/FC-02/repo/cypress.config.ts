import { defineConfig } from "cypress";

export default defineConfig({
  e2e: { baseUrl: "http://127.0.0.1:4177" },
  retries: { runMode: 2, openMode: 0 },
});
