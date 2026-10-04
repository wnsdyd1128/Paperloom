import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// 개발 서버는 /api 요청을 로컬 백엔드(ops/config/local.yaml의 127.0.0.1:8000)로 넘긴다.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
