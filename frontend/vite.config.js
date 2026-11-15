import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development the API is proxied, so the browser sees one origin
// (localhost:5173) and the sign-in cookies are first-party.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.BACKEND_URL || "http://127.0.0.1:8000";
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target: backend, changeOrigin: false },
        "/media": { target: backend, changeOrigin: false },
        "/sitemap.xml": { target: backend, changeOrigin: false },
      },
    },
  };
});
