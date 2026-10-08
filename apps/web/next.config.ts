import type { NextConfig } from "next";

const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // The verification harness builds into a run-scoped directory so parallel runs and cleanup stay exact.
  distDir: process.env.EDGE_OS_WEB_DIST ?? ".next",
  // Next rewrites the tsconfig it builds with. The harness points at a run-scoped copy so tracked files stay clean.
  typescript: { tsconfigPath: process.env.EDGE_OS_WEB_TSCONFIG ?? "tsconfig.json" },
};

export default config;
