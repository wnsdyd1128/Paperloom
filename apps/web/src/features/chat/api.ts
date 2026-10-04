/**
 * Reader "Claude와 대화" 탭이 부르는 이 PC의 Claude Code 브리지 (backend/src/paperloom/integrations/claude_code, ADR 0003).
 * 브리지 주소는 Paperloom health(claude_code_url)로 받는다. 브리지는 packet ID와 질문만 받고, 근거 글·이미지는
 * Paperloom에서 직접 읽는다. 답은 생성되는 대로 줄 단위 JSON(NDJSON)으로 온다.
 */

import type { Answer } from "../answers/api";

export type BridgeHealth = Readonly<{
  ready: boolean;
  claude: Readonly<{ installed: boolean; version?: string; logged_in?: boolean; auth_method?: string | null; subscription?: string | null }>;
  error: Readonly<{ code: string; message: string }> | null;
}>;

export type ChatModel = "sonnet" | "opus" | "haiku";
export const CHAT_MODELS: readonly Readonly<{ value: ChatModel | null; label: string }>[] = [
  { value: null, label: "기본 모델" },
  { value: "sonnet", label: "Sonnet" },
  { value: "opus", label: "Opus" },
  { value: "haiku", label: "Haiku" },
];

export type ChatEvent =
  | Readonly<{ type: "start"; run_id: string }> // 중단(cancelClaude)에 쓰는 실행 ID
  | Readonly<{ type: "delta"; text: string }>
  | Readonly<{ type: "done"; answer: Answer }>
  | Readonly<{ type: "error"; code: string; message: string }>
  | Readonly<{ type: "cancelled" }>; // 중단했다. 답은 저장하지 않았다

/** fork: session_id 대화를 이어받은 새 대화(갈래)로 묻는다. fork_at: 그 대화의 이 답까지만 이어받는다(2026-10-02 사용자 요청) */
export type ChatRequest = Readonly<{
  packet_id: string;
  question: string;
  session_id: string | null;
  model: ChatModel | null;
  fork?: boolean;
  fork_at?: string;
}>;

/** 브리지를 켜는 명령 (Windows PowerShell). <Paperloom 폴더>는 사용자 PC의 저장소 폴더다. */
export const START_COMMAND = '& "<Paperloom 폴더>\\backend\\.venv\\Scripts\\python.exe" -m paperloom.integrations.claude_code';

export async function claudeCodeUrl(): Promise<string> {
  const health = (await (await fetch("/api/v1/health")).json()) as { claude_code_url?: string };
  return health.claude_code_url ?? "http://127.0.0.1:8001";
}

/** 브리지가 꺼져 있으면 null */
export async function bridgeHealth(url: string): Promise<BridgeHealth | null> {
  try {
    const response = await fetch(`${url}/health`);
    return response.ok ? ((await response.json()) as BridgeHealth) : null;
  } catch {
    return null;
  }
}

/** 질문을 보내고 사건을 차례로 넘긴다. 실패도 error 사건으로 넘긴다(던지지 않는다). */
export async function askClaude(url: string, request: ChatRequest, onEvent: (event: ChatEvent) => void): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${url}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) });
  } catch {
    onEvent({ type: "error", code: "BRIDGE_OFFLINE", message: "Claude Code 브리지에 연결할 수 없습니다. 브리지를 켜 주세요." });
    return;
  }
  if (!response.ok || !response.body) {
    const body = (await response.json().catch(() => ({}))) as { code?: string; message?: string; detail?: unknown };
    onEvent({ type: "error", code: body.code ?? `HTTP_${response.status}`, message: body.message ?? "질문을 보내지 못했습니다." });
    return;
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let ended = false;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines.filter(Boolean)) {
      const event = JSON.parse(line) as ChatEvent;
      ended ||= event.type === "done" || event.type === "error" || event.type === "cancelled";
      onEvent(event);
    }
  }
  if (!ended) onEvent({ type: "error", code: "STREAM_CLOSED", message: "답을 받는 중에 연결이 끊겼습니다. 답이 저장됐는지 잠시 뒤 확인하세요." });
}

/**
 * 실행 중인 차례를 중단한다(2026-10-02 사용자 요청). 브리지가 Claude Code를 끝내면 그 차례의 흐름에 cancelled 사건이
 * 온다. 이미 끝났으면 false.
 */
export async function cancelClaude(url: string, runId: string): Promise<boolean> {
  try {
    const response = await fetch(`${url}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: runId }) });
    return response.ok;
  } catch {
    return false;
  }
}
