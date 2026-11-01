import { copyFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

/** /docs의 Swagger 화면 파일을 웹 빌드에 넣는다. 서버가 CDN 대신 이 파일을 쓴다(backend paperloom/api/docs.py). */
function swaggerUi(): Plugin {
  return {
    name: "paperloom-swagger-ui",
    apply: "build",
    async writeBundle({ dir }) {
      const target = resolve(dir ?? "dist", "swagger");
      await mkdir(target, { recursive: true });
      const files = ["swagger-ui-bundle.js", "swagger-ui.css", "LICENSE", "NOTICE"];
      await Promise.all(files.map((file) => copyFile(resolve("node_modules/swagger-ui-dist", file), resolve(target, file))));
    },
  };
}

// 개발 서버는 /api 요청을 로컬 백엔드(ops/config/local.yaml의 127.0.0.1:8000)로 넘긴다.
export default defineConfig({
  plugins: [react(), swaggerUi()],
  server: {
    host: "127.0.0.1",
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
