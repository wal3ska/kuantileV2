import { resolve } from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        // Ana SPA + herkese acik Quant Lab (build -> dist/quantlab/index.html,
        // nginx try_files $uri/ ile /quantlab/ olarak sunulur).
        main: resolve(__dirname, "index.html"),
        quantlab: resolve(__dirname, "quantlab/index.html"),
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
