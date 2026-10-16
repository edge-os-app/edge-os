// Isolated browser driver for the LOCAL Docker rehearsal. scripts/deployment_rehearsal/rehearsal_run.py copies this
// folder into the run's private evidence and links the accepted tests/p03 node_modules beside it.
import { defineConfig } from "@playwright/test";

const evidence = process.env.REHEARSAL_EVIDENCE_DIR ?? ".evidence";

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.mjs/,
  timeout: 90_000,
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
