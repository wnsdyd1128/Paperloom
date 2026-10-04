/**
 * 사이드바 "Claude와 대화"의 대화들. 대화는 답변의 대화 ID로 묶는다. 이름은 바꾼 이름(원문 위에서 옮겨 온 대화는 그
 * 대화 기록의 제목)이 있으면 그것을, 없으면 첫 질문 앞부분이다. 이름 바꾸기·지우기·갈래는 2026-10-02 사용자 요청
 * (backend/src/paperloom/threads, `/api/v1/chat-sessions`). 갈래는 원래 대화를 이어받은 새 Claude Code 대화다
 * (--fork-session). 갈래의 첫 답이 저장된 뒤 웹이 원래 대화를 기록한다.
 */

import { expectOk, jsonRequest, parseJson } from "../../shared/http";
import type { Answer } from "../answers/api";

export type Session = Readonly<{ id: string; title: string; updated: string }>;
/** 갈래의 이어받기: 갈라져 나온 대화와, 답에서 갈라졌으면 그 답(없으면 갈래를 만든 때까지 또는 지금까지) */
export type ForkLink = Readonly<{ parent: string; at: string | null }>;
/** 서버가 아는 대화 정보: 이름, 갈래면 이어받기 */
export type SessionMeta = Readonly<{ title: string; fork: ForkLink | null }>;
type Turns = Readonly<{ inherited: readonly Answer[]; own: readonly Answer[] }>;

const MAX_FORK_DEPTH = 20; // 잘못된 기록이 서로를 가리켜도 멈춘다

const TITLE_CHARS = 40;

/** 답변(오래된 것부터)을 대화로 묶는다. 마지막 차례가 최근인 것부터. */
export function sessionsOf(answers: readonly Answer[], titles: ReadonlyMap<string, string>): Session[] {
  const byId = new Map<string, Session>();
  for (const answer of answers) {
    if (!answer.session_id) continue;
    const known = byId.get(answer.session_id);
    const title = known?.title ?? titles.get(answer.session_id) ?? excerpt(answer.prompt ?? answer.question, TITLE_CHARS);
    byId.set(answer.session_id, { id: answer.session_id, title, updated: answer.created_at });
  }
  return [...byId.values()].sort((a, b) => b.updated.localeCompare(a.updated));
}

/**
 * 대화의 차례: 이어받은 것과 이 대화의 것. 답변은 오래된 것부터다. 갈래는 원래 대화(거슬러 올라가며)에서 갈라진 답까지,
 * 그 답을 모르면(대화 전체를 이어받은 갈래) 갈래의 첫 답 전까지를 이어받는다. session이 null이고 draft가 있으면 아직
 * 첫 답이 없는 갈래다: 갈라진 답까지, 없으면 원래 대화의 지금까지를 이어받는다.
 */
export function conversationTurns(
  answers: readonly Answer[],
  session: string | null,
  links: ReadonlyMap<string, ForkLink>,
  draft: ForkLink | null = null,
  depth = 0,
): Turns {
  if (session === null) {
    if (draft === null || depth > MAX_FORK_DEPTH) return { inherited: [], own: [] };
    return { inherited: upTo(lineage(answers, draft.parent, links, depth + 1), draft.at), own: [] };
  }
  const own = answers.filter((answer) => answer.session_id === session);
  const link = links.get(session);
  if (!link || own.length === 0 || depth > MAX_FORK_DEPTH) return { inherited: [], own };
  const upstream = lineage(answers, link.parent, links, depth + 1);
  const inherited = link.at ? upTo(upstream, link.at) : upstream.filter((answer) => answer.created_at < own[0].created_at);
  return { inherited, own };
}

function lineage(answers: readonly Answer[], session: string, links: ReadonlyMap<string, ForkLink>, depth: number): readonly Answer[] {
  const turns = conversationTurns(answers, session, links, null, depth);
  return [...turns.inherited, ...turns.own];
}

/** 그 답까지(포함). 그 답이 없으면(버렸다 등) 모두 */
function upTo(turns: readonly Answer[], at: string | null): readonly Answer[] {
  const index = at === null ? -1 : turns.findIndex((answer) => answer.answer_id === at);
  return index < 0 ? turns : turns.slice(0, index + 1);
}

/** 서버가 아는 대화 정보: 대화 ID → 이름·갈라져 나온 대화 */
export async function listSessionMeta(paperId: string): Promise<Map<string, SessionMeta>> {
  const url = `/api/v1/chat-sessions?paper_id=${encodeURIComponent(paperId)}`;
  type Row = { session_id: string; title: string; parent_session_id: string | null; fork_answer_id: string | null };
  const { sessions } = await parseJson<{ sessions: Row[] }>(await fetch(url));
  return new Map(
    sessions.map((item) => [
      item.session_id,
      { title: item.title, fork: item.parent_session_id ? { parent: item.parent_session_id, at: item.fork_answer_id } : null },
    ]),
  );
}

/** 갈래의 첫 답이 저장된 뒤 원래 대화·갈라진 답·이름을 남긴다. */
export async function recordFork(sessionId: string, paperId: string, fork: ForkLink, title: string): Promise<void> {
  const body = { paper_id: paperId, parent_session_id: fork.parent, title, ...(fork.at ? { fork_answer_id: fork.at } : {}) };
  await expectOk(await fetch(sessionUrl(sessionId) + "/fork", jsonRequest("PUT", body)));
}

/** 이름을 바꾼다. 서버가 공백을 정리한 이름을 돌려준다. */
export async function renameSession(sessionId: string, paperId: string, title: string): Promise<string> {
  const response = await fetch(sessionUrl(sessionId) + "/title", jsonRequest("PUT", { paper_id: paperId, title }));
  return (await parseJson<{ title: string }>(response)).title;
}

/** 대화를 지운다: 답을 모두 버리고 대화 기록·이름을 지운다. */
export async function deleteSession(sessionId: string): Promise<void> {
  await expectOk(await fetch(sessionUrl(sessionId), { method: "DELETE" }));
}

function sessionUrl(sessionId: string): string {
  return `/api/v1/chat-sessions/${encodeURIComponent(sessionId)}`;
}

function excerpt(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}
