import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  serverExternalPackages: ["pg"],
};

export default config;
