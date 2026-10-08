import type { NextConfig } from "next";

const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // The verification harness builds into a run-scoped directory so parallel runs and cleanup stay exact.
  distDir: process.env.EDGE_OS_WEB_DIST ?? ".next",
};

export default config;
