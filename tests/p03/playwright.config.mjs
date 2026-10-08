import { defineConfig } from "@playwright/test";

const evidence = process.env.P03_EVIDENCE_DIR ?? ".evidence";

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.mjs/,
  timeout: 60_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"], ["json", { outputFile: `${evidence}/playwright-report.json` }]],
  outputDir: `${evidence}/playwright-output`,
  use: { baseURL: process.env.P03_WEB_URL, trace: "off" },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } } },
    { name: "mobile-390", use: { viewport: { width: 390, height: 844 }, hasTouch: true } },
  ],
});
