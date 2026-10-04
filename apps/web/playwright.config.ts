import { resolve } from "node:path";

import { defineConfig } from "@playwright/test";

const root = resolve(import.meta.dirname, "../..");
const python = resolve(root, "backend/.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
/** 가짜 Claude Code CLI가 받은 인자·메시지를 남기는 곳 (e2e/chat.spec.ts가 읽는다) */
const FAKE_CLAUDE_LOG = resolve(root, "var/e2e-claude/fake-claude.jsonl");

// 우리 웹앱 검증 전용이다. ChatGPT·Claude 세션을 자동 조작하는 데 쓰지 않는다 (IMPL §14.2).
export default defineConfig({
  testDir: "e2e",
  timeout: 600_000,
  workers: 1, // 모든 project가 같은 백엔드·데이터 폴더를 쓴다
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8791", // ops/config/e2e.yaml의 port
    channel: "msedge", // 설치된 Edge를 쓴다 (브라우저 내려받기 없음)
    viewport: { width: 1280, height: 900 },
    // 없는 요소를 기다리며 테스트 제한(10분)까지 멈추지 않게 한다.
    actionTimeout: 15_000,
  },
  // PLAN A03: devicePixelRatio 3종
  projects: [1, 2, 3].map((dpr) => ({ name: `dpr-${dpr}`, use: { deviceScaleFactor: dpr } })),
  webServer: [
    {
      command: `npm run build && "${python}" -m paperloom --config "${resolve(root, "ops/config/e2e.yaml")}"`,
      url: "http://127.0.0.1:8791/api/v1/health",
      reuseExistingServer: false,
      timeout: 180_000,
    },
    // Reader "Claude와 대화" 탭의 브리지 (ADR 0003). 실제 Claude Code 대신 가짜 CLI를 실행해 사용량을 쓰지 않는다.
    {
      command: `"${python}" -m paperloom.integrations.claude_code --port 8794 --paperloom-url http://127.0.0.1:8791`,
      url: "http://127.0.0.1:8794/health",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        PAPERLOOM_CLAUDE_CLI: JSON.stringify([python, resolve(root, "tests/fixtures/fake_claude/fake_claude.py")]),
        PAPERLOOM_CLAUDE_WORK_DIR: resolve(root, "var/e2e-claude"),
        FAKE_CLAUDE_LOG: FAKE_CLAUDE_LOG,
      },
    },
  ],
});
