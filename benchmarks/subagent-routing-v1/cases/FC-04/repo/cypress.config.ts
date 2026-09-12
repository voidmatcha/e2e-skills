import { defineConfig } from "cypress";

export default defineConfig({
  viewportWidth: process.env.CI ? 640 : 1280,
  viewportHeight: 800,
  e2e: { baseUrl: "http://127.0.0.1:4178" },
});
