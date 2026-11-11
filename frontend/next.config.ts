import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // The dev indicator sat over the sidebar's Sign out button and took its clicks.
  devIndicators: false,
  // Local development on either host: Next.js blocks its dev resources from another
  // host unless it's listed (issue 266).
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
