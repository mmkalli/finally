import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

// Production is a static export served by FastAPI on the same origin.
// `next dev` has no backend of its own, so /api/* is proxied to uvicorn on :8000
// (rewrites are not allowed together with `output: "export"`). Override the target with BACKEND_URL.
const nextConfig: NextConfig = {
  ...(isDev
    ? {
        async rewrites() {
          return [{ source: "/api/:path*", destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/api/:path*` }];
        },
      }
    : { output: "export" }),
  images: { unoptimized: true },
  // gzip in the dev server buffers the proxied SSE stream, so prices would never arrive.
  compress: false,
  devIndicators: false,
  reactStrictMode: true,
};

export default nextConfig;
