import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  output: 'standalone', // Required for Docker
  turbopack: {
    root: process.cwd(), // Fix lockfile warning
  },
};

export default nextConfig;
