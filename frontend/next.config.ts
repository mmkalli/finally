import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Production is a static export served by FastAPI on the same origin, so
// `/api/*` needs no proxy. `next dev` runs on :3000, so it forwards `/api/*`
// to the backend on :8000 (rewrites can't be combined with `output: "export"`).
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export default function config(phase: string): NextConfig {
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      // Gzip would buffer the SSE stream through the dev proxy.
      compress: false,
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
      },
    };
  }
  return {
    output: "export",
    images: { unoptimized: true },
  };
}
