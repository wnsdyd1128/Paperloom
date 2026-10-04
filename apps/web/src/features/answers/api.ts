/** AI 호스트가 저장한 답변 REST 클라이언트 (backend/src/paperloom/answers/routes.py, IMPL §11.1, ADR 0002). */

import { parseJson } from "../../shared/http";
import type { EvidenceRole, Scope } from "../context/api";

/** 답변의 [number]가 가리키는 packet 근거와 그 원문 위치 */
export type Citation = Readonly<{
  number: number;
  /** 논문 본문 근거의 문단(¶, 1부터). 짚었으면 block_id가 그 문단이다 */
  paragraph: number | null;
  evidence_id: string;
  role: EvidenceRole;
  page_index: number;
  paper_id: string;
  version_id: string;
  anchor_id: string;
  block_id: string | null;
}>;

/** 답변이 딸린 packet에서 사용자가 고른 위치. 대화에서 질문 위에 인용으로 보인다 */
export type AnswerContext = Readonly<{
  /** text, 또는 영역 종류(figure·table·equation·generic) */
  kind: string;
  page_index: number;
  text: string;
  anchor_id: string;
  image_url: string | null;
}>;

export type Answer = Readonly<{
  answer_id: string;
  packet_id: string;
  /** host_mcp: Claude Desktop이 MCP 도구로 저장(2026-10-05에 뺐다 — 예전 답변), claude_code: Reader 대화 탭(이 PC의 Claude Code) */
  origin: "host_mcp" | "claude_code";
  connection_name: string | null;
  /** claude_code: 이 차례의 질문 */
  prompt: string | null;
  /** claude_code: 이어 묻기에 쓰는 대화 ID */
  session_id: string | null;
  /** 모델이 쓴 Markdown 그대로. HTML로 해석하지 않고 글자로만 보인다 */
  markdown: string;
  content_sha256: string;
  citations: readonly Citation[];
  /** packet에 없는 근거 번호 */
  unresolved_citations: readonly number[];
  review_status: "unreviewed";
  created_at: string;
  discarded_at: string | null;
  question: string;
  paper_titles: readonly string[];
  context: readonly AnswerContext[];
  /** packet의 대화 범위와 그 쪽 (U3 전 packet은 null) */
  scope: Scope | null;
  scope_page: number | null;
  /** claude_code: 이 차례가 끝난 때의 컨텍스트 길이(토큰)와 모델의 창 크기. 모르면 null (2026-10-02) */
  context_tokens: number | null;
  context_window: number | null;
  /** claude_code: 이 답에서 갈라질 자리(차례 끝 Claude Code 메시지 ID). 이 기능 전 답은 null */
  message_id: string | null;
}>;

export type AnswerQuery = Readonly<{ packetId?: string; paperId?: string; sessionId?: string; origin?: Answer["origin"]; limit?: number }>;

/** 버리지 않은 답변, 최근 것부터 */
export async function listAnswers({ packetId, paperId, sessionId, origin, limit }: AnswerQuery = {}): Promise<Answer[]> {
  const params = new URLSearchParams();
  if (packetId) params.set("packet_id", packetId);
  if (paperId) params.set("paper_id", paperId);
  if (sessionId) params.set("session_id", sessionId);
  if (origin) params.set("origin", origin);
  if (limit) params.set("limit", String(limit));
  const query = params.toString();
  return (await parseJson<{ answers: Answer[] }>(await fetch(`/api/v1/answers${query ? `?${query}` : ""}`))).answers;
}

export async function discardAnswer(answerId: string): Promise<Answer> {
  return parseJson<Answer>(await fetch(`/api/v1/answers/${encodeURIComponent(answerId)}`, { method: "DELETE" }));
}
