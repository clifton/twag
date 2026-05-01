import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const heavyDeps = [
  "react",
  "react-dom",
  "react-router",
  "@tanstack/react-query",
  "lucide-react",
  "@radix-ui/react-dialog",
  "@radix-ui/react-dropdown-menu",
  "@radix-ui/react-popover",
  "@radix-ui/react-select",
  "@radix-ui/react-slot",
  "@radix-ui/react-switch",
  "@radix-ui/react-toast",
  "@radix-ui/react-tooltip",
  "@uiw/react-codemirror",
  "codemirror",
  "@codemirror/lang-markdown",
  "@codemirror/theme-one-dark",
];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 8080,
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://localhost:5173",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  optimizeDeps: {
    include: heavyDeps,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    reportCompressedSize: false,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (!id.includes("node_modules")) return undefined;
          if (id.match(/[\\/]node_modules[\\/]react-router[\\/]/))
            return "react";
          if (
            id.match(/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/)
          )
            return "react";
          if (id.includes("@radix-ui")) return "radix";
          if (
            id.match(/[\\/]node_modules[\\/]codemirror[\\/]/) ||
            id.includes("@codemirror") ||
            id.includes("@uiw/react-codemirror") ||
            id.includes("@lezer")
          )
            return "codemirror";
          if (id.includes("@tanstack")) return "tanstack";
          if (id.includes("lucide-react")) return "lucide";
          return undefined;
        },
      },
    },
  },
});
