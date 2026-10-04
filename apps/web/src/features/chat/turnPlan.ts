/**
 * 대화 한 차례를 어떻게 보낼지 정한다 (docs/UI_PLAN.md U3). 순수 함수다.
 *
 * 범위: 논문 본문(paper) · 현재 쪽(page). "선택만"은 2026-10-04 사용자 요청으로 뺐다(고른 위치는 첨부로 붙인다).
 * 같은 대화(Claude Code 세션)에 이미 보낸 본문은 다시 보내지 않는다(구독 사용량). 그래서
 * - 붙인 위치가 있으면 새 packet이다. 범위 본문을 그 대화에 아직 보내지 않았을 때만 함께 넣는다(보냈으면 범위 selection).
 * - 붙인 위치가 없으면, 범위 본문을 이미 보냈으면 앞 차례의 packet으로 질문만 보내고, 아니면 범위 본문으로 새 packet을 만든다.
 * U3 전에 만든 packet(범위 없음)은 본문을 보냈다고 보지 않는다.
 */

import type { Anchor } from "../annotations/api";
import type { Answer } from "../answers/api";
import type { Intent, PacketRequest, Scope } from "../context/api";

/** 대화창에서 고르는 범위 */
export type ChatScope = Extract<Scope, "paper" | "page">;

export type TurnInput = Readonly<{
  question: string;
  scope: ChatScope;
  /** 지금 보고 있는 쪽 (0부터) */
  pageIndex: number;
  versionId: string;
  attachments: readonly Anchor[];
  /** 이 대화의 차례들, 오래된 것부터 */
  turns: readonly Pick<Answer, "scope" | "scope_page" | "packet_id">[];
  intent?: Intent;
  /** 논문 본문 한도. 없으면 서버 기본값(120,000자) */
  paperTextChars?: number;
}>;

export type TurnPlan = Readonly<{ kind: "reuse"; packetId: string }> | Readonly<{ kind: "new"; request: PacketRequest }>;

export function planTurn({ question, scope, pageIndex, versionId, attachments, turns, intent = "ask", paperTextChars }: TurnInput): TurnPlan {
  const scopeSent = turns.some((turn) => turn.scope === scope && (scope !== "page" || turn.scope_page === pageIndex));
  const scopeText: Partial<PacketRequest> = {
    scope,
    version_id: versionId,
    ...(scope === "page" ? { page_index: pageIndex } : {}),
    ...(scope === "paper" && paperTextChars ? { paper_text_chars: paperTextChars } : {}),
  };
  const anchors = attachments.map((anchor) => ({ anchor_id: anchor.anchor_id, include_context: true, include_image: true }));
  if (anchors.length > 0) {
    return { kind: "new", request: { intent, question, anchors, ...(scopeSent ? { scope: "selection" } : scopeText) } };
  }
  const last = turns.at(-1);
  if (scopeSent && last) return { kind: "reuse", packetId: last.packet_id };
  return { kind: "new", request: { intent, question, anchors: [], ...scopeText } };
}
