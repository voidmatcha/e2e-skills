// Apache-2.0.
import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests', workers:1, fullyParallel:false, retries:0, timeout:10000, expect:{timeout:1500}, use:{baseURL:'http://127.0.0.1:__PORT__', trace:'on'}, webServer:{command:'node app.mjs', url:'http://127.0.0.1:__PORT__/health', reuseExistingServer:false}});
