import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command:
        "cd ../backend && ../.venv/bin/python -m tests.e2e_m1_3_server",
      url: "http://127.0.0.1:8100/healthz",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command:
        "SHIGUANG_API_PROXY=http://127.0.0.1:8100 npm run dev -- --hostname 127.0.0.1 --port 3100",
      url: "http://127.0.0.1:3100/agent",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
