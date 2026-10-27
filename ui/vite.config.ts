import path from "path";
import { fileURLToPath } from "url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 开发时前端跑 vite dev，/events /send 代理到 Node 桥（ui/server.mjs，默认 8765）
const BRIDGE = process.env.ZICAT_BRIDGE ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    proxy: {
      "/events": BRIDGE,
      "/send": BRIDGE,
    },
  },
});
