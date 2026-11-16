import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Inside Compose the API is reachable as http://api:8000, not localhost.
  const apiTarget = env["API_PROXY_TARGET"] ?? "http://localhost:8000";

  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        // The browser calls /api/..., the dev server forwards it to the API without the prefix.
        "/api": {
          target: apiTarget,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
