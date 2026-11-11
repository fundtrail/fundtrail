import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // The dev indicator sat over the sidebar's Sign out button and took its clicks.
  devIndicators: false,
};

export default nextConfig;
