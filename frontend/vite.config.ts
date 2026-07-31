import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const mcpName = "patient_summary_card";

export default defineConfig(({ command }) => {
  const isBuild = command === "build";

  return {
    plugins: isBuild ? [react(), viteSingleFile()] : [react()],
    root: path.resolve(__dirname, "mcp", mcpName),
    base: "/__/frontend/",
    envDir: path.resolve(__dirname, "../web"),
    resolve: {
      alias: {
        "@api": path.resolve(__dirname, "../web/src/api"),
      },
      dedupe: ["react", "react-dom", "zod"],
    },
    server: {
      port: parseInt(process.env.RBT_VITE_PORT || "4444", 10),
      strictPort: true,
      host: true,
      allowedHosts: true,
    },
    build: {
      outDir: path.resolve(__dirname, "dist/mcp", mcpName),
      emptyOutDir: true,
      assetsInlineLimit: 100000000,
      cssCodeSplit: false,
      rollupOptions: {
        output: {
          inlineDynamicImports: true,
        },
      },
    },
  };
});
