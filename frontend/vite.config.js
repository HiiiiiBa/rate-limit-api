import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/dashboard/",
  build: {
    outDir: "../static/dashboard",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true, ws: true },
      "/users": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/products": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
