/// <reference types="vitest" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";

// Transform .css imports inside node_modules to empty stubs (e.g. @agentscope-ai/*).
const cssStubPlugin = {
  name: "css-stub",
  transform(_code: string, id: string) {
    if (id.includes("node_modules") && id.endsWith(".css")) {
      return { code: "export default {}" };
    }
  },
};

const packageJson = JSON.parse(
  readFileSync(path.resolve(__dirname, "package.json"), "utf8"),
) as { version?: string };

const resolveCommit = () => {
  try {
    return execSync("git rev-parse --short HEAD", {
      cwd: path.resolve(__dirname, "../../../.."),
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    return "";
  }
};

const padBuildPart = (value: number) => value.toString().padStart(2, "0");

const resolveBuildId = () => {
  const now = new Date();
  return [
    now.getFullYear().toString().slice(2),
    padBuildPart(now.getMonth() + 1),
    padBuildPart(now.getDate()),
    padBuildPart(now.getHours()),
    padBuildPart(now.getMinutes()),
  ].join("");
};

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBaseUrl = env.VITE_API_BASE_URL ?? "";
  const agentdeskVersion = env.VITE_AGENTDESK_VERSION ?? packageJson.version ?? "0.0.0";
  const agentdeskBuild = env.VITE_AGENTDESK_BUILD ?? resolveBuildId();
  const agentdeskCommit = env.VITE_AGENTDESK_COMMIT ?? resolveCommit();

  return {
    define: {
      VITE_API_BASE_URL: JSON.stringify(apiBaseUrl),
      VITE_AGENTDESK_VERSION: JSON.stringify(agentdeskVersion),
      VITE_AGENTDESK_BUILD: JSON.stringify(agentdeskBuild),
      VITE_AGENTDESK_COMMIT: JSON.stringify(agentdeskCommit),
      TOKEN: JSON.stringify(env.TOKEN || ""),
    },
    plugins: [tailwindcss(), react(), cssStubPlugin],
    css: {
      modules: {
        localsConvention: "camelCase",
        generateScopedName: "[name]__[local]__[hash:base64:5]",
      },
      preprocessorOptions: { less: { javascriptEnabled: true } },
    },
    resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
    server: {
      host: "0.0.0.0",
      port: 5182,
      allowedHosts: true,
      proxy: {
        "/api": { target: "http://127.0.0.1:8088", changeOrigin: true },
        "/health": { target: "http://127.0.0.1:8088", changeOrigin: true },
      },
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: true,
      testTimeout: 120_000,
      hookTimeout: 120_000,
      pool: "forks",
      maxWorkers: 1,
      alias: {
        "@agentscope-ai/design": path.resolve(
          __dirname,
          "src/test/design-mock.ts",
        ),
        "@agentscope-ai/chat": path.resolve(
          __dirname,
          "src/test/chat-mock.ts",
        ),
      },
    },
    build: {
      outDir: path.resolve(__dirname, "../static_next"),
      emptyOutDir: true,
      cssCodeSplit: true,
      sourcemap: false,
      chunkSizeWarningLimit: 500,
      rollupOptions: {
        output: {
          experimentalMinChunkSize: 8000,
          manualChunks: undefined,
        },
      },
    },
  };
});
