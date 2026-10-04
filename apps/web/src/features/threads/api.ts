/** 선택 설명·질문 대화 REST 클라이언트 (backend/src/paperloom/threads/routes.py, docs/UI_PLAN.md A4). */

import { expectOk, jsonRequest, parseJson, postJson } from "../../shared/http";
import type { Anchor } from "../annotations/api";

export type ThreadKind = "explain" | "translate" | "ask";
export type Placement = "inline" | "sidebar";

export type Thread = Readonly<{
  /** 이 PC의 Claude Code 대화 ID (답변의 session_id) */
  session_id: string;
  paper_id: string;
  anchor: Anchor;
  kind: ThreadKind;
  title: string;
  /** inline: 원문 위 창, sidebar: 사이드바 대화로 옮김 */
  placement: Placement;
  answer_count: number;
  last_answer_at: string | null;
  created_at: string;
  updated_at: string;
}>;

export const THREAD_KIND_LABELS: Readonly<Record<ThreadKind, string>> = { explain: "설명", translate: "번역", ask: "질문" };

/** 답변 화면의 대화 한 줄 (U6, 사용자 결정 D8). kind chat은 사이드바에서 시작한 대화다. */
export type Conversation = Readonly<{
  session_id: string;
  kind: "chat" | ThreadKind;
  title: string;
  paper_id: string;
  paper_title: string;
  version_id: string;
  placement: Placement | null;
  anchor_id: string | null;
  page_index: number | null;
  answer_count: number;
  last_answer_at: string;
}>;

/** 모든 논문의 Claude Code 대화, 마지막 답이 최근인 것부터 */
export async function listConversations(): Promise<Conversation[]> {
  return (await parseJson<{ conversations: Conversation[] }>(await fetch("/api/v1/conversations"))).conversations;
}

export async function listThreads(paperId: string): Promise<Thread[]> {
  const url = `/api/v1/chat-threads?paper_id=${encodeURIComponent(paperId)}`;
  return (await parseJson<{ threads: Thread[] }>(await fetch(url))).threads;
}

/** 첫 답을 받은 뒤 남긴다. 같은 대화 ID를 다시 보내면 앞의 것을 준다. */
export async function saveThread(body: Readonly<{ session_id: string; paper_id: string; anchor_id: string; kind: ThreadKind; title: string }>): Promise<Thread> {
  return parseJson<Thread>(await postJson("/api/v1/chat-threads", body));
}

export async function moveThread(sessionId: string, placement: Placement): Promise<Thread> {
  return parseJson<Thread>(await fetch(threadUrl(sessionId), jsonRequest("PATCH", { placement })));
}

/** 대화를 지우고 그 대화의 답변을 버린다. */
export async function deleteThread(sessionId: string): Promise<void> {
  await expectOk(await fetch(threadUrl(sessionId), { method: "DELETE" }));
}

function threadUrl(sessionId: string): string {
  return `/api/v1/chat-threads/${encodeURIComponent(sessionId)}`;
}
