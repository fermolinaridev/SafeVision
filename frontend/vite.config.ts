import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: Object.fromEntries(
      ["/auth", "/detect", "/events", "/analytics", "/cameras", "/videos", "/health", "/docs", "/openapi.json", "/creditos"]
        .map((path) => [path, { target: "http://127.0.0.1:7860", ws: true }]),
    ),
  },
});
