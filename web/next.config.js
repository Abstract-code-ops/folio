/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "jdvyoywfzvfrcckaytmm.supabase.co",
      },
    ],
  },
};

module.exports = nextConfig;
