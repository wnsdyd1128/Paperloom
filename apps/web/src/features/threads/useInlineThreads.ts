import { useEffect, useRef, useState } from "react";

import type { Anchor } from "../annotations/api";
import { type Answer, listAnswers } from "../answers/api";
import { askClaude, cancelClaude } from "../chat/api";
import { type ContextPacket, createPacket, getPacket, type PacketRequest } from "../context/api";
import { deleteThread, listThreads, moveThread, saveThread, type Thread, type ThreadKind } from "./api";

/**
 * 원문 위에서 이어지는 설명·번역·질문 대화 하나. key는 화면 안에서만 쓰는 이름이다(불러온 대화는 대화 ID,
 * 새로 연 것은 임시 이름). 첫 답이 저장되면 thread(서버 기록)가 생긴다.
 */
export type InlineThread = Readonly<{
  key: string;
  kind: ThreadKind;
  anchor: Anchor;
  title: string;
  thread: Thread | null;
  /** 첫 질문의 packet (보낸 근거). 불러온 대화는 펼칠 때 받는다 */
  packet: ContextPacket | null;
  /** 차례들, 오래된 것부터. null이면 아직 불러오지 않음 */
  answers: readonly Answer[] | null;
  /** 답을 만드는 중인 차례. runId는 중단에 쓰는 브리지 실행 ID(첫 사건에서 받는다) */
  pending: Readonly<{ prompt: string; text: string; runId?: string }> | null;
  error: string | null;
}>;

type Options = Readonly<{
  paperId: string;
  /** 브리지 주소 (health에서 받는다) */
  bridgeUrl: () => Promise<string>;
  onBridgeOffline: () => void;
}>;

const TITLE_CHARS = 60;
const LIST_LIMIT = 200;

/**
 * 선택 메뉴의 설명·번역·질문 대화 (docs/UI_PLAN.md U2·A4·A5). 한 번에 하나만 펼치고 나머지는 원문 위 칩으로 접는다.
 * 묻기는 Reader 대화 탭과 같은 브리지(ADR 0003)를 쓴다: 고른 위치로 packet을 만들고 새 대화로 묻는다.
 */
export function useInlineThreads({ paperId, bridgeUrl, onBridgeOffline }: Options) {
  const [items, setItems] = useState<readonly InlineThread[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  // 원문 위 창에서 지운 대화. 사이드바 대화가 먼저 읽어 둔 답에서도 계속 가린다(지운 대화가 거기 나타나 다시 지우면 실패했다)
  const [removed, setRemoved] = useState<ReadonlySet<string>>(new Set());
  const itemsRef = useRef(items);
  itemsRef.current = items;

  useEffect(() => {
    let cancelled = false;
    setItems([]);
    setExpanded(null);
    setLoaded(false);
    setRemoved(new Set());
    listThreads(paperId)
      .then((threads) => {
        if (!cancelled) setItems(threads.map(fromThread));
      })
      .catch(() => undefined) // 목록을 못 받아도 새로 묻는 것은 된다
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [paperId]);

  const update = (key: string, change: (item: InlineThread) => InlineThread) =>
    setItems((current) => current.map((item) => (item.key === key ? change(item) : item)));

  /** 한 차례를 묻는다. 첫 차례면 대화 기록을 남긴다. */
  async function turn(key: string, packetId: string, question: string, sessionId: string | null) {
    update(key, (item) => ({ ...item, pending: { prompt: question, text: "" }, error: null }));
    let answer: Answer | null = null;
    await askClaude(await bridgeUrl(), { packet_id: packetId, question, session_id: sessionId, model: null }, (event) => {
      if (event.type === "start") update(key, (item) => ({ ...item, pending: item.pending && { ...item.pending, runId: event.run_id } }));
      if (event.type === "delta") update(key, (item) => ({ ...item, pending: item.pending && { ...item.pending, text: item.pending.text + event.text } }));
      if (event.type === "cancelled") update(key, (item) => ({ ...item, error: "답 만들기를 중단했습니다." }));
      if (event.type === "done") answer = event.answer;
      if (event.type === "error") {
        update(key, (item) => ({ ...item, error: event.message }));
        if (event.code === "BRIDGE_OFFLINE") onBridgeOffline();
      }
    });
    const saved = answer as Answer | null;
    update(key, (item) => ({ ...item, pending: null, answers: saved ? [...(item.answers ?? []), saved] : item.answers }));
    const current = itemsRef.current.find((item) => item.key === key);
    if (saved && current && !current.thread && saved.session_id) {
      const title = current.kind === "explain" ? (firstHeading(saved.markdown) ?? current.title) : current.title;
      try {
        const thread = await saveThread({ session_id: saved.session_id, paper_id: paperId, anchor_id: current.anchor.anchor_id, kind: current.kind, title });
        update(key, (item) => ({ ...item, thread, title: thread.title }));
      } catch {
        update(key, (item) => ({ ...item, error: "대화 기록을 남기지 못했습니다. 답은 저장됐습니다." }));
      }
    }
  }

  return {
    items,
    /** 원문 위 창에서 지운 대화 ID (사이드바 대화 기록에서도 가린다) */
    removed,
    /** 저장된 대화 목록을 받았는지 (못 받았어도 true) */
    loaded,
    expanded,
    busy: items.some((item) => item.pending !== null),

    /** 고른 위치로 새 대화를 열고 바로 묻는다. */
    async start(kind: ThreadKind, anchor: Anchor, question: string) {
      const key = `new-${Date.now()}`;
      const title = kind === "ask" ? excerpt(question, TITLE_CHARS) : anchorTitle(anchor);
      const item: InlineThread = { key, kind, anchor, title, thread: null, packet: null, answers: [], pending: { prompt: question, text: "" }, error: null };
      setItems((current) => [...current, item]);
      setExpanded(key);
      let packet: ContextPacket;
      try {
        packet = await createPacket(firstPacketRequest(kind, anchor, question));
      } catch {
        update(key, (current) => ({ ...current, pending: null, error: "Claude에게 보낼 문맥을 만들지 못했습니다. 백엔드 연결을 확인하세요." }));
        return;
      }
      update(key, (current) => ({ ...current, packet }));
      await turn(key, packet.packet_id, question, null);
    },

    /** 같은 대화에서 이어서 묻는다(질문만 보낸다). */
    async followUp(key: string, question: string) {
      const item = itemsRef.current.find((candidate) => candidate.key === key);
      const last = item?.answers?.at(-1);
      if (!item || !last?.session_id) return;
      await turn(key, last.packet_id, question, last.session_id);
    },

    /** 답을 만드는 중인 차례를 중단한다. 답은 저장하지 않는다. */
    async stop(key: string) {
      const runId = itemsRef.current.find((candidate) => candidate.key === key)?.pending?.runId;
      if (runId) await cancelClaude(await bridgeUrl(), runId);
    },

    /** 펼친다. 불러온 대화면 그 차례와 첫 packet을 받는다. */
    async expand(key: string) {
      setExpanded(key);
      const item = itemsRef.current.find((candidate) => candidate.key === key);
      if (!item?.thread || item.answers !== null) return;
      try {
        const answers = [...(await listAnswers({ sessionId: item.thread.session_id, origin: "claude_code", limit: LIST_LIMIT }))].reverse();
        const packet = answers[0] ? await getPacket(answers[0].packet_id) : null;
        update(key, (current) => ({ ...current, answers, packet }));
      } catch {
        update(key, (current) => ({ ...current, answers: [], error: "대화를 불러오지 못했습니다." }));
      }
    },

    collapse() {
      setExpanded(null);
    },

    /** 대화를 지운다(답변도 버린다). 첫 답 전이면 창만 닫는다. */
    async remove(key: string) {
      const item = itemsRef.current.find((candidate) => candidate.key === key);
      if (item?.thread) {
        const session = item.thread.session_id;
        await deleteThread(session);
        setRemoved((current) => new Set(current).add(session));
      }
      setItems((current) => current.filter((candidate) => candidate.key !== key));
      setExpanded((current) => (current === key ? null : current));
    },

    /** 사이드바 대화에서 대화 이름을 바꿨다(원문 위에서 옮겨 온 대화면 그 제목). */
    sessionRenamed(sessionId: string, title: string) {
      setItems((current) => current.map((item) => (item.thread?.session_id === sessionId ? { ...item, title, thread: { ...item.thread, title } } : item)));
    },

    /** 사이드바 대화에서 대화를 지웠다. */
    sessionDeleted(sessionId: string) {
      setItems((current) => current.filter((item) => item.thread?.session_id !== sessionId));
    },

    /** 사이드바 대화에서 답을 버렸다. */
    answerDiscarded(answer: Answer) {
      setItems((current) => withoutAnswer(current, answer));
    },

    /** 사이드바 대화로 옮긴다. 옮긴 기록을 돌려준다. */
    async moveToSidebar(key: string): Promise<Thread | null> {
      const item = itemsRef.current.find((candidate) => candidate.key === key);
      if (!item?.thread) return null;
      const thread = await moveThread(item.thread.session_id, "sidebar");
      update(key, (current) => ({ ...current, thread }));
      setExpanded((current) => (current === key ? null : current));
      return thread;
    },
  };
}

export type InlineThreads = ReturnType<typeof useInlineThreads>;

/** 차례 수. 이 화면에서 차례를 불러왔거나 이어 물었으면 그것을, 아니면 서버 기록의 개수를 쓴다. */
export function answerCount(item: InlineThread): number {
  return item.answers?.length ?? item.thread?.answer_count ?? 0;
}

/**
 * 다른 곳(사이드바 대화의 "버리기")에서 버린 답을 뺀다. 답이 하나도 남지 않은 대화는 목록에서 뺀다. 서버도 그런 대화는
 * 목록에 주지 않는다(2026-10-02 사용자 확인: "답변 0"인 대화가 남았다). 그 대화가 없으면 같은 배열을 돌려준다.
 */
export function withoutAnswer(items: readonly InlineThread[], answer: Pick<Answer, "answer_id" | "session_id">): readonly InlineThread[] {
  if (!items.some((item) => item.thread?.session_id === answer.session_id)) return items;
  return items.flatMap((item) => {
    if (!item.thread || item.thread.session_id !== answer.session_id) return [item];
    const next: InlineThread = {
      ...item,
      thread: { ...item.thread, answer_count: Math.max(0, item.thread.answer_count - 1) },
      answers: item.answers?.filter((candidate) => candidate.answer_id !== answer.answer_id) ?? null,
    };
    return answerCount(next) === 0 ? [] : [next];
  });
}

/** 마지막 차례의 시각 */
export function lastAnswerAt(item: InlineThread): string | null {
  return item.answers?.at(-1)?.created_at ?? item.thread?.last_answer_at ?? item.thread?.created_at ?? null;
}

/**
 * 새 대화의 첫 packet. 설명·질문은 고른 위치를 앞세우고 논문 앞쪽부터 고른 쪽 다음 쪽까지와 참고문헌 쪽을 보낸다(범위 until_page,
 * 서버 기본 한도. 마지막 쪽을 고르면 서버가 문서 끝까지로 줄인다). 2026-10-02 사용자 요청: 고른 곳만 보내면 논문의 정의를 몰라
 * 일반 지식으로 채웠다. 같은 날 앞뒤 한 쪽(around_page)으로 줄였다가 2026-10-04 사용자 요청으로 바꿨다("18 페이지에서 고르면
 * 1–18pp + 19pp를 의도했는데 17–19pp만 잡힌다"): 앞에서 정의한 것을 뒤에서 쓴다. 번역은 문장 단위라 본문 없이 고른 글과
 * 앞뒤 문단만 보낸다(사용량). 대화는 고를 때마다 따로다.
 */
export function firstPacketRequest(kind: ThreadKind, anchor: Anchor, question: string): PacketRequest {
  const anchors = [{ anchor_id: anchor.anchor_id, include_context: true, include_image: true }];
  if (kind === "translate") return { intent: kind, question, anchors };
  return { intent: kind, question, anchors, scope: "until_page", version_id: anchor.version_id, page_index: anchor.page_index + 1 };
}

function fromThread(thread: Thread): InlineThread {
  return { key: thread.session_id, kind: thread.kind, anchor: thread.anchor, title: thread.title, thread, packet: null, answers: null, pending: null, error: null };
}

/** 답의 첫 소제목 (설명 대화의 제목, A5). Markdown 강조 기호(*, **, __, `)는 빼고, 낱말 속 밑줄(U_tot)은 둔다. */
export function firstHeading(markdown: string): string | null {
  const match = /^#{1,6}\s+(.+?)\s*#*\s*$/m.exec(markdown);
  const text = match?.[1].replace(/\*+|__|`/g, "").trim();
  return text ? excerpt(text, TITLE_CHARS) : null;
}

/** 고른 글 앞부분, 영역이면 종류와 쪽 */
export function anchorTitle(anchor: Anchor): string {
  if (anchor.kind !== "text") return `${REGION_TITLES[anchor.kind] ?? "영역"} · ${anchor.page_index + 1}쪽`;
  return excerpt(anchor.display_quote ?? anchor.quote, TITLE_CHARS);
}

const REGION_TITLES: Readonly<Record<string, string>> = { figure: "그림", table: "표", equation: "수식", generic: "영역" };

export function excerpt(text: string, limit: number): string {
  const tidy = text.replace(/\s+/g, " ").trim();
  return tidy.length > limit ? `${tidy.slice(0, limit)}…` : tidy;
}
