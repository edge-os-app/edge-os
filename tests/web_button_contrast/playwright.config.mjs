import { defineConfig } from "@playwright/test";

const evidence = process.env.BUTTON_CONTRAST_EVIDENCE_DIR ?? ".evidence";

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.mjs/,
  timeout: 60_000,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: `${evidence}/playwright-report.json` }]],
  outputDir: `${evidence}/playwright-output`,
  use: { trace: "off" },
  projects: [
    { name: "desktop-1280", use: { browserName: "chromium", viewport: { width: 1280, height: 800 } } },
    { name: "mobile-390-hover-none", use: { browserName: "chromium", viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
});
