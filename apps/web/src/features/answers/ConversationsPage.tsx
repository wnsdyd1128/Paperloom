/**
 * 답변 화면 (U6, 사용자 결정 D8): 모든 논문의 Claude Code 대화를 최근 순으로. 사이드바 대화와 원문 위에서 시작한
 * 설명·번역·질문. 누르면 그 논문을 열고 그 대화를 사이드바(사이드바 대화)나 원문 위(원문 위 대화)에서 연다.
 * 아래에는 공유한 문맥에 Claude Desktop이 저장한 답변(ADR 0002, D1 보류)이 있으면 보인다.
 */
import { useEffect, useState } from "react";

import { relativeTime } from "../../shared/time";
import { type Conversation, listConversations, THREAD_KIND_LABELS } from "../threads/api";
import type { Citation } from "./api";
import { AnswerList } from "./AnswerList";

const KIND_LABELS: Readonly<Record<Conversation["kind"], string>> = { chat: "대화", ...THREAD_KIND_LABELS };

type State = Readonly<{ kind: "loading" }> | Readonly<{ kind: "ready"; items: readonly Conversation[] }> | Readonly<{ kind: "failed" }>;

type Props = Readonly<{
  onOpen: (conversation: Conversation) => void;
  onOpenCitation: (citation: Citation) => void;
}>;

export function ConversationsPage({ onOpen, onOpenCitation }: Props) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    listConversations()
      .then((items) => setState({ kind: "ready", items }))
      .catch(() => setState({ kind: "failed" }));
  }, []);

  return (
    <section className="shelf conversations" aria-labelledby="answers-heading">
      <div className="shelf-head">
        <div className="shelf-title">
          <h2 id="answers-heading">답변</h2>
          {/* 서버는 최근 대화를 100개까지 준다 (GET /conversations 기본 limit) */}
          {state.kind === "ready" && <span className="shelf-count">{state.items.length >= 100 ? "최근 대화 100개" : `대화 ${state.items.length}개`}</span>}
        </div>
      </div>
      {state.kind === "loading" && <p className="muted">대화를 불러오는 중…</p>}
      {state.kind === "failed" && <p className="status error">대화를 불러오지 못했습니다. 백엔드 연결을 확인하세요.</p>}
      {state.kind === "ready" && state.items.length === 0 && (
        <p className="muted">아직 대화가 없습니다. 논문을 열고 "Claude와 대화"나 글을 골라 설명·번역·질문을 해 보세요.</p>
      )}
      {state.kind === "ready" && state.items.length > 0 && (
        <ol className="conversation-list">
          {state.items.map((item) => (
            <li key={item.session_id} data-session-id={item.session_id}>
              <button type="button" className="conversation-row" onClick={() => onOpen(item)}>
                <span className={item.kind === "chat" ? "tag tag-outline" : "tag tag-neutral"}>{KIND_LABELS[item.kind]}</span>
                <span className="conversation-when">{relativeTime(item.last_answer_at)}</span>
                <span className="conversation-title">{item.title}</span>
                <span className="conversation-paper">
                  {item.paper_title}
                  {item.page_index !== null && ` · p.${item.page_index + 1}`}
                </span>
                <span className="conversation-count">답변 {item.answer_count}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
      <section className="desktop-answers" aria-labelledby="desktop-answers-heading">
        <h3 id="desktop-answers-heading">Claude Desktop에서 저장한 답변</h3>
        <AnswerList hideOrigin="claude_code" onShowCitation={onOpenCitation} emptyText="없습니다. (Claude Desktop 공유 화면은 지금 꺼져 있습니다.)" />
      </section>
    </section>
  );
}
