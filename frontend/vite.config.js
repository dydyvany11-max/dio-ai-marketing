import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/vk": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/vkid": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/trends": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/system": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
