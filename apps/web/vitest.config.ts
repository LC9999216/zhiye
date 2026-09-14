import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // preserveSymlinks 跳过 vite 8 的真实路径解析（该步骤在受限环境
  // 无法 spawn 子进程，会抛 EPERM）。
  resolve: {
    preserveSymlinks: true,
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: ["./tests/setup.ts"],
  },
});
