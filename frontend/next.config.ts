import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    // Gốc là chính thư mục frontend/: DO_AN/ còn có package-lock.json riêng, và nếu để Turbopack lấy
    // DO_AN/ làm gốc thì nó sẽ theo dõi cả backend/.venv (rất nhiều file) -> tốn RAM/CPU khi dev.
    root: path.join(__dirname),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
