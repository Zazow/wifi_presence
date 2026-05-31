import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy API + WebSocket to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on all interfaces so you can open the dev UI from a phone on the
    // same network (needed for "Register this device").
    host: true,
    port: 5280,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true,
        // Forward the client's real IP as X-Forwarded-For so the backend's
        // /api/whoami can identify the phone behind the dev proxy.
        xfwd: true,
      },
    },
  },
});
