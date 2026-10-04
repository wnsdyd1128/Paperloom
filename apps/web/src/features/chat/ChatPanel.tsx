import { type FormEvent, Fragment, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";
import { formatTime, relativeTime } from "../../shared/time";
import type { Anchor } from "../annotations/api";
import { type Answer, type AnswerContext, type Citation, discardAnswer, listAnswers } from "../answers/api";
import { AnswerMarkdown } from "../answers/AnswerMarkdown";
import { findCitation } from "../answers/citations";
import { type ContextPacket, createPacket, EVIDENCE_ROLE_LABELS, type Intent } from "../context/api";
import { formatMathForCopy } from "../../shared/mathCopy";
import { approxPages } from "../settings/api";
import { usePreferences } from "../settings/PreferencesProvider";
import { askClaude, cancelClaude, CHAT_MODELS, type ChatModel } from "./api";
import { type Bridge, BridgeStatus } from "./BridgeStatus";
import {
  conversationTurns,
  deleteSession,
  type ForkLink,
  listSessionMeta,
  recordFork,
  renameSession,
  type Session,
  type SessionMeta,
  sessionsOf,
} from "./sessions";
import { type ChatScope, planTurn } from "./turnPlan";

/**
 * Reader가 대화 칸에 넘기는 일. nonce가 바뀔 때마다 한 번 처리한다.
 * - ask: 이 packet으로 바로 묻는다.
 * - attach: 고른 위치를 입력칸에 붙인다. text가 있으면 입력칸에 넣는다(원문 위 질문 창을 옮긴 경우).
 * - open: 그 대화를 연다(원문 위 대화를 사이드바로 옮긴 경우).
 * - summary: 지금 대화에서 논문 본문 범위로 3줄 요약을 묻는다(머리의 "3줄 요약", A9).
 */
export type ChatRequest =
  | Readonly<{ kind: "ask"; packet: ContextPacket; nonce: number }>
  | Readonly<{ kind: "attach"; anchor: Anchor; text?: string; nonce: number }>
  | Readonly<{ kind: "open"; sessionId: string; nonce: number }>
  | Readonly<{ kind: "summary"; nonce: number }>;

export const SUMMARY_QUESTION = "이 논문을 세 줄로 요약해 주세요. 해결하려는 문제, 핵심 방법, 주요 결과를 한 줄씩 쓰세요.";

// 논문 본문 한도는 설정(기본 설정 · 논문 본문 한도)에서 온다. 서버도 같은 설정으로 자른다.
const SCOPES: readonly Readonly<{ value: ChatScope; label: string; title: (paperChars: number) => string }>[] = [
  { value: "paper", label: "논문 본문", title: (paperChars) => `논문 본문을 앞쪽부터 ${paperChars.toLocaleString("ko-KR")}자(한 단 논문 약 ${approxPages(paperChars)}쪽)까지 함께 보냅니다. 한 대화에 한 번만 보냅니다` },
  { value: "page", label: "현재 쪽", title: () => "지금 보고 있는 쪽의 본문을 함께 보냅니다. 한 대화에 쪽마다 한 번만 보냅니다" },
];
const SCOPE_KEY = "paperloom.chat.scope"; // 이 브라우저에서만 기억하는 편의 설정

function storedScope(): ChatScope {
  try {
    // 예전에 기억한 "선택만"(2026-10-04에 뺐다)은 논문 본문으로 연다
    return localStorage.getItem(SCOPE_KEY) === "page" ? "page" : "paper";
  } catch {
    return "paper";
  }
}

type Props = Readonly<{
  paperId: string;
  /** 범위(논문 본문·현재 쪽)의 본문을 읽을 논문 버전 */
  versionId: string;
  /** 지금 보고 있는 쪽 (0부터). 범위 "현재 쪽"이 보낸다 */
  pageIndex: number;
  bridge: Bridge;
  request: ChatRequest | null;
  /** 이 패널이 보이는지. 보이게 되면 입력칸에 포커스를 둔다 */
  visible: boolean;
  /** 원문 위 창에서 이어지는 대화. 사이드바 대화 목록에서 뺀다 */
  hiddenSessions: ReadonlySet<string>;
  onShowCitation: (citation: Citation) => void;
  onShowAnchor: (anchorId: string) => void;
  onShowPage: (pageNumber: number) => void;
  /** 답을 버렸을 때 (선택 설명·질문 목록이 그 대화의 차례 수를 맞춘다) */
  onDiscarded: (answer: Answer) => void;
  /** 대화 이름을 바꿨을 때·대화를 지웠을 때 (원문 위에서 옮겨 온 대화면 선택 설명·질문 목록도 맞춘다) */
  onSessionRenamed: (sessionId: string, title: string) => void;
  onSessionDeleted: (sessionId: string) => void;
}>;

type Pending = Readonly<{ prompt: string; quote: readonly AnswerContext[]; text: string }>;
/** 아직 첫 답이 없는 갈래: 이어받을 대화, 갈라진 답(대화 전체면 null), 갈래의 이름 */
type ForkDraft = ForkLink & Readonly<{ title: string }>;

const LIST_LIMIT = 200;

/**
 * Reader 오른쪽 사이드바의 "Claude와 대화" (ADR 0003, 시안 3a–3c). 논문마다 대화가 이어진다: 입력칸에서 묻거나,
 * 고른 위치를 붙여 묻는다. 답은 생성되는 대로 Markdown으로 보이고, 근거 번호·쪽 표기를 누르면 원문 위치로 간다.
 * 모델은 이 PC의 Claude Code가 사용자의 Claude 구독 사용량으로 실행한다. 질문과 답은 검토 전 답변으로 남는다.
 * 답을 만드는 중에는 보내기 단추가 중단 단추다. 갈래는 지금 대화를 이어받은 새 대화이고, 이어받은 차례를 흐리게
 * 보인다. 지금 대화의 컨텍스트 길이(마지막 차례 끝 기준)를 제목 아래에 보인다 (2026-10-02 사용자 요청).
 */
export function ChatPanel({ paperId, versionId, pageIndex, bridge, request, visible, hiddenSessions, onShowCitation, onShowAnchor, onShowPage, onDiscarded, onSessionRenamed, onSessionDeleted }: Props) {
  const [answers, setAnswers] = useState<readonly Answer[]>([]); // 이 논문의 대화 답, 오래된 것부터
  // undefined: 아직 고르지 않음(가장 최근 대화를 연다), null: 새 대화
  const [chosen, setChosen] = useState<string | null | undefined>(undefined);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [meta, setMeta] = useState<ReadonlyMap<string, SessionMeta>>(new Map()); // 이름·갈라져 나온 대화
  const [fork, setFork] = useState<ForkDraft | null>(null);
  const [runId, setRunId] = useState<string | null>(null); // 지금 실행 중인 차례(중단용)
  const [notice, setNotice] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [attachments, setAttachments] = useState<readonly Anchor[]>([]);
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState<ChatScope>(storedScope);
  const [model, setModel] = useState<ChatModel | null>(null);
  const { preferences } = usePreferences();
  const [error, setError] = useState<string | null>(null);
  const handled = useRef<number | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const reload = () =>
    listAnswers({ paperId, origin: "claude_code", limit: LIST_LIMIT }).then((list) => {
      const ordered = [...list].reverse();
      setAnswers(ordered);
      return ordered;
    });

  const reloadMeta = () => listSessionMeta(paperId).then(setMeta);

  useEffect(() => {
    void reload().catch(() => undefined);
    void reloadMeta().catch(() => undefined);
  }, [paperId]);

  const titles = new Map([...meta].map(([id, item]) => [id, item.title]));
  const links = new Map([...meta].flatMap(([id, item]) => (item.fork ? [[id, item.fork] as const] : [])));
  const sessions = sessionsOf(answers, titles).filter((item) => !hiddenSessions.has(item.id));
  const session = chosen === undefined ? (sessions[0]?.id ?? null) : chosen !== null && hiddenSessions.has(chosen) ? null : chosen;
  const sessionRef = useRef<string | null>(session);
  sessionRef.current = session;
  const forkRef = useRef<ForkDraft | null>(fork);
  forkRef.current = fork;

  useEffect(() => {
    if (!request || handled.current === request.nonce) return;
    handled.current = request.nonce;
    if (request.kind === "ask") {
      void send(request.packet.packet_id, request.packet.question, packetQuote(request.packet));
    } else if (request.kind === "attach") {
      setAttachments((current) =>
        current.some((anchor) => anchor.anchor_id === request.anchor.anchor_id) ? current : [...current, request.anchor],
      );
      if (request.text) setQuestion(request.text);
      inputRef.current?.focus();
    } else if (request.kind === "summary") {
      if (pending) setError("앞 질문의 답을 만드는 중입니다. 끝난 뒤 다시 누르세요.");
      else void ask(SUMMARY_QUESTION, "paper", "summarize", false);
    } else {
      void Promise.all([reload(), reloadMeta()])
        .then(() => setChosen(request.sessionId))
        .catch(() => setError("대화를 불러오지 못했습니다."));
    }
  }, [request]);

  // 사용자가 패널을 열 때만 입력칸에 포커스를 둔다. Reader를 처음 열 때는 본문이 포커스를 가진다(키보드 쪽 이동·선택 단축키).
  const wasVisible = useRef(visible);
  useEffect(() => {
    if (visible && !wasVisible.current) inputRef.current?.focus();
    wasVisible.current = visible;
  }, [visible]);

  // 갈래면 이어받은 차례도 대화의 일부다(모델이 그 차례를 안다). 범위 본문을 다시 보낼지도 그것까지 보고 정한다.
  const { inherited, own } = conversationTurns(answers, session, links, fork && { parent: fork.parent, at: fork.at });
  const turns = [...inherited, ...own];

  // 새 답이 오면 맨 아래로 내린다.
  useEffect(() => {
    const list = messagesRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [turns.length, pending?.text, session]);

  async function send(packetId: string, prompt: string, quote: readonly AnswerContext[]) {
    setError(null);
    setNotice(null);
    setPending({ prompt, quote, text: "" });
    const url = await bridge.resolveUrl();
    const draft = forkRef.current; // 갈래면 원래 대화를 이어받은 새 대화로 묻는다
    const forking = draft ? { fork: true, ...(draft.at ? { fork_at: draft.at } : {}) } : {};
    const body = { packet_id: packetId, question: prompt, session_id: draft?.parent ?? sessionRef.current, model, ...forking };
    await askClaude(url, body, (event) => {
      if (event.type === "start") setRunId(event.run_id);
      if (event.type === "delta") setPending((current) => current && { ...current, text: current.text + event.text });
      if (event.type === "done") {
        const created = event.answer.session_id;
        setAnswers((current) => [...current, event.answer]);
        if (draft && created) {
          const link = { parent: draft.parent, at: draft.at };
          setMeta((current) => new Map(current).set(created, { title: draft.title, fork: link }));
          setFork(null);
          void recordFork(created, paperId, link, draft.title).catch(() => setError("갈래를 기록하지 못했습니다. 답은 저장됐습니다."));
        }
        setChosen(created);
      }
      if (event.type === "cancelled") {
        setNotice("답 만들기를 중단했습니다. 질문은 입력칸에 돌려 두었습니다.");
        setQuestion((current) => current || prompt);
      }
      if (event.type === "error") {
        setError(event.message);
        if (event.code === "BRIDGE_OFFLINE") bridge.markOffline();
      }
    });
    setRunId(null);
    setPending(null);
  }

  async function stop() {
    if (runId && !(await cancelClaude(await bridge.resolveUrl(), runId))) setError("이미 끝난 차례입니다.");
  }

  /**
   * 갈래를 시작한다. at이 없으면 지금 대화 전체를, 있으면 그 답(이어받은 차례면 그 답이 든 원래 대화의 그 답)까지를
   * 이어받는다. 첫 질문을 보내면 Claude Code가 새 대화를 만든다.
   */
  function startFork(at: Answer | null) {
    const parent = at?.session_id ?? session;
    if (!parent) return;
    setFork({ parent, at: at?.answer_id ?? null, title: `${title} (갈래)` });
    setChosen(null);
    setHistoryOpen(false);
    inputRef.current?.focus();
  }

  /**
   * 한 차례를 묻는다. 범위 본문을 이 대화에 이미 보냈으면 질문만, 아니면 새 packet으로 보낸다(turnPlan.ts).
   * 보내지 못하면 false를 돌려준다(입력칸 글은 그대로 둔다).
   */
  async function ask(prompt: string, askScope: ChatScope, intent: Intent = "ask", withAttachments = true): Promise<boolean> {
    const plan = planTurn({ question: prompt, scope: askScope, pageIndex, versionId, attachments: withAttachments ? attachments : [], turns, intent });
    let packetId = plan.kind === "reuse" ? plan.packetId : "";
    let quote: readonly AnswerContext[] = [];
    if (plan.kind === "new") {
      try {
        const packet = await createPacket(plan.request);
        [packetId, quote] = [packet.packet_id, packetQuote(packet)];
      } catch {
        setError("질문을 만들지 못했습니다. 백엔드 연결을 확인하세요.");
        return false;
      }
    }
    if (withAttachments) setAttachments([]);
    await send(packetId, prompt, quote);
    return true;
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const prompt = question.trim();
    if (!prompt || pending) return;
    const sent = question;
    setQuestion("");
    if (!(await ask(prompt, scope))) setQuestion(sent);
  }

  const chooseScope = (value: ChatScope) => {
    setScope(value);
    try {
      localStorage.setItem(SCOPE_KEY, value);
    } catch {
      // 기억하지 못해도 이번 화면에서는 바뀐다
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 조합 중의 Enter는 글자를 마무리하는 것이므로 보내지 않는다.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };

  const discard = (answer: Answer) =>
    void discardAnswer(answer.answer_id)
      .then(() => {
        setAnswers((current) => current.filter((item) => item.answer_id !== answer.answer_id));
        onDiscarded(answer);
      })
      .catch(() => setError("답을 버리지 못했습니다."));

  async function rename(item: Session, title: string) {
    setRenaming(null);
    if (!title.trim() || title.trim() === item.title) return;
    try {
      const saved = await renameSession(item.id, paperId, title);
      setMeta((current) => new Map(current).set(item.id, { title: saved, fork: current.get(item.id)?.fork ?? null }));
      onSessionRenamed(item.id, saved);
    } catch {
      setError("대화 이름을 바꾸지 못했습니다.");
    }
  }

  async function remove(item: Session) {
    if (!window.confirm(`"${item.title}" 대화를 지울까요? 답도 모두 버립니다.`)) return;
    try {
      await deleteSession(item.id);
    } catch {
      setError("대화를 지우지 못했습니다.");
      return;
    }
    setAnswers((current) => current.filter((answer) => answer.session_id !== item.id));
    if (item.id === session) setChosen(null);
    onSessionDeleted(item.id);
  }

  const choose = (id: string | null) => {
    setChosen(id);
    setFork(null);
    setHistoryOpen(false);
  };

  const health = bridge.health === "checking" ? null : bridge.health;
  const ready = health?.ready === true;
  const title = fork?.title ?? sessions.find((item) => item.id === session)?.title ?? "새 대화";
  const measured = [...turns].reverse().find((answer) => answer.context_tokens !== null);
  return (
    <section className="chat-panel" aria-labelledby="chat-heading">
      <header className="side-head is-strong">
        <h2 id="chat-heading" className="side-title">
          Claude와 대화
        </h2>
        <button
          type="button"
          className="btn btn-icon side-tool"
          aria-label="대화 기록"
          aria-expanded={historyOpen}
          title="대화 기록"
          onClick={() => setHistoryOpen((open) => !open)}
          disabled={pending !== null}
        >
          <Icon name="history" size={16} />
        </button>
        <button
          type="button"
          className="btn btn-icon side-tool"
          aria-label="갈래 만들기"
          title="지금 대화를 이어받은 새 대화(갈래)를 만듭니다. 원래 대화는 그대로 남습니다"
          onClick={() => startFork(null)}
          disabled={pending !== null || session === null}
        >
          <Icon name="fork" size={16} />
        </button>
        <button
          type="button"
          className="btn btn-icon side-tool"
          aria-label="새 대화"
          title="새 대화"
          onClick={() => choose(null)}
          disabled={pending !== null || (session === null && fork === null)}
        >
          <Icon name="plus" size={16} />
        </button>
      </header>
      <button type="button" className="chat-title-row" onClick={() => setHistoryOpen((open) => !open)} disabled={pending !== null} aria-label={`지금 대화: ${title}. 대화 기록 열기`}>
        <span className="chat-title">{title}</span>
        <Icon name={historyOpen ? "chevronUp" : "chevronDown"} size={14} />
      </button>
      {historyOpen && (
        <ul className="chat-history" aria-label="이 논문의 대화">
          <li>
            <button type="button" className={session === null && fork === null ? "is-active" : undefined} onClick={() => choose(null)}>
              <span>새 대화</span>
            </button>
          </li>
          {sessions.map((item) => (
            <li key={item.id} className="chat-history-item" data-session-id={item.id}>
              {renaming === item.id ? (
                <RenameField title={item.title} onDone={(title) => void rename(item, title)} />
              ) : (
                <>
                  <button type="button" className={item.id === session ? "is-active" : undefined} onClick={() => choose(item.id)}>
                    <span>{item.title}</span>
                    <small>{relativeTime(item.updated)}</small>
                  </button>
                  <button type="button" className="chat-history-tool" aria-label={`${item.title} 이름 바꾸기`} title="이름 바꾸기" onClick={() => setRenaming(item.id)}>
                    <Icon name="pencil" size={13} />
                  </button>
                  <button type="button" className="chat-history-tool" aria-label={`${item.title} 지우기`} title="지우기" onClick={() => void remove(item)}>
                    <Icon name="trash" size={13} />
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {!ready && <BridgeStatus bridge={bridge} />}
      <div className="chat-messages" ref={messagesRef} aria-live="polite">
        {turns.length === 0 && !pending && <ChatGuide />}
        {turns.map((answer, index) => (
          <Fragment key={answer.answer_id}>
            {index === inherited.length && index > 0 && <ForkDivider />}
            <Turn
              answer={answer}
              inherited={index < inherited.length}
              showQuote={turns[index - 1]?.packet_id !== answer.packet_id}
              onShowCitation={onShowCitation}
              onShowAnchor={onShowAnchor}
              onShowPage={onShowPage}
              onDiscard={discard}
              onFork={pending ? null : startFork}
            />
          </Fragment>
        ))}
        {inherited.length > 0 && own.length === 0 && <ForkDivider />}
        {pending && (
          <div className="chat-turn is-pending">
            <UserBubble prompt={pending.prompt} quote={pending.quote} onShowAnchor={onShowAnchor} />
            <div className="chat-answer">
              {pending.text ? (
                <AnswerMarkdown markdown={pending.text} canCite={() => false} onCite={() => undefined} />
              ) : (
                <p className="chat-thinking muted">답을 만드는 중…</p>
              )}
            </div>
          </div>
        )}
      </div>
      {error && (
        <p className="status error chat-error" role="status">
          {error}
        </p>
      )}
      {notice && !error && (
        <p className="status chat-error" role="status">
          {notice}
        </p>
      )}
      <form className="chat-composer" onSubmit={(event) => void submit(event)}>
        {attachments.length > 0 && (
          <ul className="chat-attachments" aria-label="질문에 붙인 위치">
            {attachments.map((anchor) => (
              <li key={anchor.anchor_id} className="chat-chip">
                <span>
                  <b>
                    {anchor.kind === "text" ? "선택" : (REGION_LABELS[anchor.kind] ?? "영역")} · p.{anchor.page_index + 1}
                  </b>{" "}
                  {anchor.kind === "text" ? excerpt(anchor.display_quote ?? anchor.quote, 80) : ""}
                </span>
                <button
                  type="button"
                  aria-label="붙인 위치 빼기"
                  onClick={() => setAttachments((current) => current.filter((item) => item.anchor_id !== anchor.anchor_id))}
                >
                  <Icon name="x" size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <textarea
          ref={inputRef}
          className="input chat-input"
          aria-label="질문"
          rows={3}
          value={question}
          placeholder="무엇이든 질문하세요"
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="chat-composer-bar">
          <label className="chip-select" title={SCOPES.find((item) => item.value === scope)?.title(preferences.paper_text_chars)}>
            <span className="chip-select-label">범위:</span>
            <select aria-label="범위" value={scope} onChange={(event) => chooseScope(event.target.value as ChatScope)}>
              {SCOPES.map((item) => (
                <option key={item.value} value={item.value} title={item.title(preferences.paper_text_chars)}>
                  {item.label}
                </option>
              ))}
            </select>
            <Icon name="chevronDown" size={12} />
          </label>
          <label className="chip-select">
            <select aria-label="모델" value={model ?? ""} onChange={(event) => setModel((event.target.value || null) as ChatModel | null)}>
              {CHAT_MODELS.map((choice) => (
                <option key={choice.label} value={choice.value ?? ""}>
                  {choice.value === null ? `${choice.label} (${CHAT_MODELS.find((item) => item.value === preferences.default_model)?.label})` : choice.label}
                </option>
              ))}
            </select>
            <Icon name="chevronDown" size={12} />
          </label>
          {measured?.context_tokens != null && <ContextRing tokens={measured.context_tokens} window={measured.context_window} />}
          {pending ? (
            <button type="button" className="send-button is-large is-stop" aria-label="중단" title="답 만들기를 멈춥니다" onClick={() => void stop()} disabled={runId === null}>
              <Icon name="stop" size={14} />
            </button>
          ) : (
            <button type="submit" className="send-button is-large" aria-label="보내기" disabled={!ready || !question.trim()}>
              <Icon name="arrowUp" size={16} />
            </button>
          )}
        </div>
        <p className="chat-note">이 PC의 Claude Code · 구독 사용량. 고른 근거와 질문이 Anthropic으로 전송됩니다.</p>
      </form>
    </section>
  );
}

/** 갈래가 이어받은 차례와 그 뒤 차례 사이 */
function ForkDivider() {
  return <p className="chat-fork-divider">여기서 갈라짐 · 위 차례는 원래 대화에서 이어받았습니다</p>;
}

const RING_RADIUS = 8;
const RING_LENGTH = 2 * Math.PI * RING_RADIUS;

/**
 * 지금 대화의 컨텍스트 길이 (마지막 차례 끝 기준). 입력칸 도구줄의 원형 아이콘으로, 채운 만큼이 창 크기에 대한 비율이다.
 * 숫자는 마우스를 올리면(title) 보이고 화면 낭독기는 이름으로 읽는다. 창 크기를 모르면 빈 원이다.
 */
function ContextRing({ tokens, window }: { tokens: number; window: number | null }) {
  const share = window ? Math.min(1, tokens / window) : 0;
  const label = `컨텍스트 ${tokens.toLocaleString()}${window ? ` / ${window.toLocaleString()}` : ""} 토큰${window ? ` · ${Math.round(share * 100)}%` : ""}`;
  return (
    <span className="context-ring" role="img" aria-label={label} title={label}>
      <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
        <circle className="context-ring-track" cx="10" cy="10" r={RING_RADIUS} />
        {share > 0 && (
          <circle
            className="context-ring-value"
            cx="10"
            cy="10"
            r={RING_RADIUS}
            strokeDasharray={`${Math.max(share * RING_LENGTH, 1.5)} ${RING_LENGTH}`}
            transform="rotate(-90 10 10)"
          />
        )}
      </svg>
    </span>
  );
}

function Turn({
  answer,
  inherited = false,
  showQuote,
  onShowCitation,
  onShowAnchor,
  onShowPage,
  onDiscard,
  onFork,
}: {
  answer: Answer;
  /** 갈래가 이어받은 차례: 흐리게 보이고 버리지 못한다(원래 대화의 답이다) */
  inherited?: boolean;
  showQuote: boolean;
  onShowCitation: (citation: Citation) => void;
  onShowAnchor: (anchorId: string) => void;
  onShowPage: (pageNumber: number) => void;
  onDiscard: (answer: Answer) => void;
  /** 이 답까지 이어받은 갈래를 시작한다. 답을 만드는 중이면 null */
  onFork: ((answer: Answer) => void) | null;
}) {
  const cite = (number: number, paragraph: number | null) => findCitation(answer.citations, number, paragraph);
  const { preferences } = usePreferences();
  return (
    <div className={inherited ? "chat-turn is-inherited" : "chat-turn"} data-answer-id={answer.answer_id}>
      <UserBubble prompt={answer.prompt ?? answer.question} quote={showQuote ? answer.context : []} onShowAnchor={onShowAnchor} />
      <div className="chat-answer">
        <AnswerMarkdown
          markdown={answer.markdown}
          canCite={(number, paragraph) => cite(number, paragraph) !== undefined}
          onCite={(number, paragraph) => onShowCitation(cite(number, paragraph)!)}
          onPage={onShowPage}
        />
        {answer.unresolved_citations.length > 0 && (
          <p className="status error">문맥에 없는 근거 번호: {answer.unresolved_citations.map((number) => `근거 ${number}`).join(", ")}</p>
        )}
        <div className="chat-answer-bar">
          <span title={answer.citations.map((c) => `근거 ${c.number} · ${EVIDENCE_ROLE_LABELS[c.role] ?? "고른 영역"} · ${c.page_index + 1}쪽`).join("\n")}>
            {formatTime(answer.created_at)}
          </span>
          <button
            type="button"
            className="btn btn-icon answer-tool"
            aria-label="복사"
            title="답 복사"
            onClick={() => void navigator.clipboard?.writeText(formatMathForCopy(answer.markdown, preferences.math_delimiters))}
          >
            <Icon name="copy" size={14} />
          </button>
          <button
            type="button"
            className="btn btn-icon answer-tool"
            aria-label="여기서 갈래"
            disabled={!onFork || !answer.message_id}
            title={answer.message_id ? "여기서 갈래: 이 답까지 이어받은 새 대화를 만듭니다" : "이 기능 전에 저장한 답이라 여기서 갈라질 수 없습니다"}
            onClick={() => onFork?.(answer)}
          >
            <Icon name="fork" size={14} />
          </button>
          {!inherited && (
            <button
              type="button"
              className="btn btn-icon answer-tool"
              aria-label="버리기"
              title="이 답 버리기"
              onClick={() => {
                if (window.confirm("이 답을 버릴까요? 대화에서 사라집니다.")) onDiscard(answer);
              }}
            >
              <Icon name="trash" size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function UserBubble({ prompt, quote, onShowAnchor }: { prompt: string; quote: readonly AnswerContext[]; onShowAnchor: (anchorId: string) => void }) {
  return (
    <div className="chat-user">
      {quote.map((item) => (
        <button key={item.anchor_id} type="button" className="chat-quote" onClick={() => onShowAnchor(item.anchor_id)} title="원문에서 보기">
          {item.image_url ? <img src={item.image_url} alt={`${item.page_index + 1}쪽 영역`} loading="lazy" /> : <span>{excerpt(item.text, 160)}</span>}
          <small>
            {item.kind === "text" ? "글" : (REGION_LABELS[item.kind] ?? "영역")} · {item.page_index + 1}쪽
          </small>
        </button>
      ))}
      <p className="chat-prompt answer-prompt">{prompt}</p>
    </div>
  );
}

function ChatGuide() {
  const { preferences } = usePreferences();
  return (
    <div className="chat-guide">
      <p>아래 입력칸에 바로 물어보거나, 논문에서 글이나 그림을 고르세요. 고르면 곁에 메뉴가 뜹니다.</p>
      <ul>
        <li>
          아래 <strong>범위</strong>로 함께 보낼 본문을 고릅니다: 논문 본문(앞쪽부터 {preferences.paper_text_chars.toLocaleString("ko-KR")}자, 약 {approxPages(preferences.paper_text_chars)}쪽), 현재 쪽. 같은 대화에 한 번 보낸 본문은 다시
          보내지 않습니다.
        </li>
        <li>
          <strong>설명</strong>·<strong>번역</strong>·<strong>AI에게 질문</strong>은 고른 자리 위의 창에서 답합니다. 창의 <strong>사이드바로 옮기기</strong>로
          여기서 이어 갈 수 있습니다.
        </li>
        <li>답의 "근거 1" 같은 근거 표시나 p.19 같은 쪽 표기를 누르면 원문 위치로 갑니다. [12] 같은 번호는 논문의 참고문헌입니다.</li>
      </ul>
    </div>
  );
}

const REGION_LABELS: Readonly<Record<string, string>> = { figure: "그림", table: "표", equation: "수식", generic: "영역" };

function packetQuote(packet: ContextPacket): AnswerContext[] {
  return packet.evidence
    .filter((item) => item.role === "selected_text" || item.role === "selected_region")
    .map((item) => ({
      kind: item.role === "selected_text" ? "text" : (item.kind ?? "generic"),
      page_index: item.page_index,
      text: item.role === "selected_text" ? (item.display_text ?? item.text) : "",
      anchor_id: item.anchor_id,
      image_url: item.image?.url ?? null,
    }));
}

/** 대화마다 첫 질문을 제목으로, 최근 대화부터 */
/** 대화 이름 고치기 칸. Enter·칸 밖을 누르면 그 이름으로, Esc면 그대로 둔다. */
function RenameField({ title, onDone }: { title: string; onDone: (title: string) => void }) {
  const [value, setValue] = useState(title);
  // Esc 뒤 칸이 사라지며 blur가 또 와도 한 번만 끝낸다(고친 이름으로 저장하지 않는다).
  const done = useRef(false);
  const finish = (next: string) => {
    if (done.current) return;
    done.current = true;
    onDone(next);
  };
  return (
    <input
      className="input chat-rename"
      aria-label="대화 이름"
      value={value}
      maxLength={200}
      autoFocus
      onFocus={(event) => event.target.select()}
      onChange={(event) => setValue(event.target.value)}
      onBlur={() => finish(value)}
      onKeyDown={(event) => {
        if (event.nativeEvent.isComposing) return;
        if (event.key === "Enter") event.currentTarget.blur();
        if (event.key === "Escape") finish(title);
      }}
    />
  );
}

function excerpt(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}
