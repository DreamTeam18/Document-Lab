import { fileURLToPath } from "node:url";

/** @type {import("next").NextConfig} */
const config = {
  devIndicators: false,
  turbopack: {
    root: fileURLToPath(new URL(".", import.meta.url)),
  },
};

export default config;
