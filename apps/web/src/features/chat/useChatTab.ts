/**
 * 원문 탭(Reader) 쪽의 대화 탭 연결 (channel.ts). 사이드바 대화를 분리하면 대화 탭을 열고, 분리한 동안 맡길 일을 그 탭에
 * 보내고, 대화 탭이 보낸 근거·위치·쪽 이동과 대화 변경을 Reader에 전한다. 지금 버전·쪽·뺄 대화는 바뀔 때마다 알린다.
 * 대화 탭이 열려 있는지(분리했는지)는 대화 탭이 알린다: 열리면 분리, 닫히면 사이드바로 돌아온다.
 */
import { useCallback, useEffect, useMemo, useRef } from "react";

import { formatRoute } from "../../app/route";
import type { Answer, Citation } from "../answers/api";
import type { ChatRequest } from "./ChatPanel";
import { type ChatChannel, openChatChannel, type ReaderState, showChatTab } from "./channel";

type Options = Readonly<{
  paperId: string;
  versionId: string;
  /** 지금 보고 있는 쪽 (0부터) */
  pageIndex: number;
  /** 원문 위에서 이어지는 대화. 대화 탭의 대화 목록에서 뺀다 */
  hiddenSessions: ReadonlySet<string>;
  /** 대화 탭이 열렸다(true) · 닫혔다(false) */
  onDetached: (detached: boolean) => void;
  onShowCitation: (citation: Citation) => void;
  onShowAnchor: (anchorId: string) => void;
  onShowPage: (pageNumber: number) => void;
  onDiscarded: (answer: Answer) => void;
  onSessionRenamed: (sessionId: string, title: string) => void;
  onSessionDeleted: (sessionId: string) => void;
  /** 브라우저가 새 탭을 막았을 때 */
  onBlocked: () => void;
}>;

export type ChatTab = Readonly<{
  /**
   * 대화 탭을 열거나 앞으로 가져온다. 사용자가 누른 동안에 불러야 한다. 막혔으면 false.
   * sessionId를 주면 대화 탭이 그 대화를 연다(사이드바에서 보던 대화를 그대로 분리한다).
   */
  show: (sessionId?: string | null) => boolean;
  /** 대화 탭에 일을 맡긴다. 방금 연 탭이면 그 탭이 준비됐다고 알릴 때 보낸다 */
  send: (request: ChatRequest) => void;
  /** 대화 탭을 닫게 하고 사이드바 대화로 돌아온다(사이드바로 되돌리기) */
  close: () => void;
}>;

export function useChatTab(options: Options): ChatTab {
  const { paperId, versionId, pageIndex, hiddenSessions } = options;
  const latest = useRef(options);
  latest.current = options;
  const readerId = useMemo(() => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`, []); // 이 원문 탭의 이름일 뿐이다
  const channel = useRef<ChatChannel | null>(null);
  const waiting = useRef(false); // 방금 연 대화 탭이 아직 준비됐다고 알리지 않았다
  const pending = useRef<ChatRequest | null>(null);
  const closing = useRef(false); // 준비되기 전에 되돌렸다: 준비되면 닫게 한다
  const detached = useRef(false);
  const unanswered = useRef<number | null>(null); // 열려 있는지 물은 뒤 답을 기다리는 타이머

  const setDetached = (value: boolean) => {
    if (unanswered.current !== null) window.clearTimeout(unanswered.current);
    unanswered.current = null;
    detached.current = value;
    latest.current.onDetached(value);
  };

  const state = (): ReaderState => {
    const current = latest.current;
    return { readerId, versionId: current.versionId, pageIndex: current.pageIndex, hiddenSessions: [...current.hiddenSessions] };
  };

  useEffect(() => {
    const opened = openChatChannel(paperId, (message) => {
      const current = latest.current;
      if (message.type === "hello") {
        waiting.current = false;
        if (closing.current) {
          closing.current = false;
          pending.current = null;
          opened.post({ type: "close" });
          return;
        }
        setDetached(true);
        opened.post({ type: "reader", state: state() });
        if (pending.current) opened.post({ type: "request", request: pending.current });
        pending.current = null;
      } else if (message.type === "chat-open") setDetached(true);
      else if (message.type === "chat-gone") setDetached(false);
      else if (message.type === "show-citation") current.onShowCitation(message.citation);
      else if (message.type === "show-anchor") current.onShowAnchor(message.anchorId);
      else if (message.type === "show-page") current.onShowPage(message.pageNumber);
      else if (message.type === "discarded") current.onDiscarded(message.answer);
      else if (message.type === "renamed") current.onSessionRenamed(message.sessionId, message.title);
      else if (message.type === "deleted") current.onSessionDeleted(message.sessionId);
    });
    channel.current = opened;
    // 대화 탭이 이미 열려 있으면(이 탭을 새로 고쳤거나 논문을 다시 열었다) 그 탭이 "chat-open"으로 답한다
    opened.post({ type: "reader", state: state() });
    const gone = () => opened.post({ type: "reader-gone", readerId });
    window.addEventListener("pagehide", gone);
    // 대화 탭이 닫혔다는 소식은 닫는 방식에 따라 오지 않을 수 있다(탭을 강제로 없애면 pagehide가 없다). 그래서 이 탭이 다시
    // 보이거나 포커스를 받을 때 대화 탭이 열려 있는지 묻고, 1초 안에 답이 없으면 사이드바로 돌아온다
    const check = () => {
      if (document.visibilityState !== "visible" || !detached.current || waiting.current || unanswered.current !== null) return;
      opened.post({ type: "ping" });
      unanswered.current = window.setTimeout(() => {
        unanswered.current = null;
        if (!waiting.current) setDetached(false);
      }, 1000);
    };
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    return () => {
      gone();
      window.removeEventListener("pagehide", gone);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check);
      if (unanswered.current !== null) window.clearTimeout(unanswered.current);
      opened.close();
      channel.current = null;
    };
  }, [paperId]);

  const hiddenKey = [...hiddenSessions].sort().join(" ");
  useEffect(() => {
    channel.current?.post({ type: "reader", state: state() });
  }, [versionId, pageIndex, hiddenKey]);

  const send = useCallback((request: ChatRequest) => {
    if (waiting.current) pending.current = request;
    else channel.current?.post({ type: "request", request });
  }, []);

  const show = useCallback(
    (sessionId?: string | null) => {
      const current = latest.current;
      const url = formatRoute({ kind: "chat", paperId: current.paperId, versionId: current.versionId, page: current.pageIndex + 1, session: sessionId ?? null });
      const fresh = showChatTab(current.paperId, url);
      if (fresh === null) {
        current.onBlocked();
        return false;
      }
      closing.current = false;
      if (fresh) waiting.current = true;
      else if (sessionId) send({ kind: "open", sessionId, nonce: Date.now() });
      setDetached(true);
      return true;
    },
    [send],
  );

  const close = useCallback(() => {
    if (waiting.current) closing.current = true; // 아직 불러오는 탭은 소식을 받지 못한다
    else channel.current?.post({ type: "close" });
    setDetached(false);
  }, []);

  return useMemo(() => ({ show, send, close }), [show, send, close]);
}
