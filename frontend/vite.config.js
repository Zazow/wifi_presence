import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy API + WebSocket to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
