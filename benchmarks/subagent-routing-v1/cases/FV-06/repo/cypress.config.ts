import { defineConfig } from "cypress";

export default defineConfig({
  e2e: { baseUrl: "https://shared-library-staging.example" },
  env: { apiOrigin: "https://shared-library-staging.example/api", dataScope: "shared" },
});
