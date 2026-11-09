/**
 * 사이드바에서 분리한 Claude와 대화 탭 (2026-11-09 사용자 요청: 대화 칸의 "새 탭으로 분리" 단추). 대화 칸(ChatPanel)은
 * 사이드바의 것 그대로다. 원문 탭과는 channel.ts로 이어진다: 범위(논문 본문·현재 쪽)는 원문 탭의 버전·쪽을 쓰고,
 * 근거·위치·쪽을 누르면 원문 탭이 그곳을 연다. 원문 탭이 없으면 그곳을 새 탭의 Reader로 연다.
 * 이 탭이 열려 있는 동안 원문 탭의 사이드바 대화는 쉬고, 이 탭을 닫거나 "사이드바로 되돌리기"를 누르면 사이드바로 돌아간다.
 * 답의 아티팩트는 이 탭에서 대화 옆 창으로 연다(좁은 창이면 대화 위에 겹친다).
 */
import { useEffect, useRef, useState } from "react";

import { formatRoute, type Route } from "../../app/route";
import type { Citation } from "../answers/api";
import type { Artifact } from "../artifacts/artifact";
import { ArtifactWindow } from "../artifacts/ArtifactWindow";
import { getPaper, type Paper } from "../library/api";
import { listThreads } from "../threads/api";
import { useBridge } from "./BridgeStatus";
import { type ChatChannel, openChatChannel, type ReaderState } from "./channel";
import { ChatPanel, type ChatRequest } from "./ChatPanel";
// 대화 칸의 모양(side-head·chat-*)은 Reader와 같은 스타일을 쓴다
import "../reader/reader.css";
import "./chatTab.css";

type ChatRoute = Extract<Route, { kind: "chat" }>;

export function ChatTab({ route }: Readonly<{ route: ChatRoute }>) {
  const [paper, setPaper] = useState<Paper | null | "failed">(null);

  useEffect(() => {
    let cancelled = false;
    getPaper(route.paperId).then(
      (loaded) => !cancelled && setPaper(loaded),
      () => !cancelled && setPaper("failed"),
    );
    return () => {
      cancelled = true;
    };
  }, [route.paperId]);

  if (paper === null) return <p className="status pending">대화를 불러오는 중…</p>;
  if (paper === "failed") {
    return (
      <p className="status error" role="status">
        논문을 불러오지 못했습니다. 백엔드 연결을 확인하세요.
      </p>
    );
  }
  return <ChatTabView paper={paper} route={route} />;
}

function ChatTabView({ paper, route }: Readonly<{ paper: Paper; route: ChatRoute }>) {
  const paperId = paper.paper_id;
  const bridge = useBridge();
  const [readers, setReaders] = useState<ReadonlyMap<string, ReaderState>>(new Map());
  const [reader, setReader] = useState<ReaderState | null>(null); // 마지막에 알린 원문 탭
  const [ownHidden, setOwnHidden] = useState<ReadonlySet<string>>(new Set()); // 원문 탭이 없을 때 뺄 원문 위 대화
  const [request, setRequest] = useState<ChatRequest | null>(() => (route.session ? { kind: "open", sessionId: route.session, nonce: Date.now() } : null));
  const [artifact, setArtifact] = useState<{ artifact: Artifact; nonce: number } | null>(null);
  const [returned, setReturned] = useState(false); // 사이드바로 되돌렸는데 브라우저가 이 탭을 닫지 못했다
  const channel = useRef<ChatChannel | null>(null);
  const greeted = useRef(new Set<string>()); // "chat-open"으로 답한 원문 탭

  /** 원문 탭의 사이드바로 되돌린다. 이 탭은 닫는다(스크립트가 연 탭이 아니면 브라우저가 막으므로 안내만 남긴다) */
  const returnedRef = useRef(false);
  const returnToSidebar = () => {
    channel.current?.post({ type: "chat-gone" });
    returnedRef.current = true; // 남은 탭은 원문 탭에 더 답하지 않는다(사이드바 대화가 다시 쉬지 않게)
    setReturned(true);
    window.close();
  };

  useEffect(() => {
    document.title = `Claude와 대화 · ${paper.title}`;
  }, [paper.title]);

  useEffect(() => {
    listThreads(paperId)
      .then((threads) => setOwnHidden(new Set(threads.filter((thread) => thread.placement !== "sidebar").map((thread) => thread.session_id))))
      .catch(() => undefined);
  }, [paperId]);

  useEffect(() => {
    const opened = openChatChannel(paperId, (message) => {
      if (returnedRef.current) return;
      if (message.type === "reader") {
        // 새로 연 원문 탭에는 이 탭이 열려 있다고 알린다(그 탭의 사이드바 대화가 쉰다)
        if (!greeted.current.has(message.state.readerId)) opened.post({ type: "chat-open" });
        greeted.current.add(message.state.readerId);
        setReaders((current) => new Map(current).set(message.state.readerId, message.state));
        setReader(message.state);
      } else if (message.type === "ping") {
        opened.post({ type: "chat-open" });
      } else if (message.type === "close") {
        returnToSidebar();
      } else if (message.type === "reader-gone") {
        setReaders((current) => {
          const next = new Map(current);
          next.delete(message.readerId);
          return next;
        });
        setReader((current) => (current?.readerId === message.readerId ? null : current));
      } else if (message.type === "request") {
        setRequest(message.request);
      }
    });
    channel.current = opened;
    opened.post({ type: "hello" });
    // 이 탭을 닫으면 원문 탭의 대화가 사이드바로 돌아간다
    const gone = () => !returnedRef.current && opened.post({ type: "chat-gone" });
    window.addEventListener("pagehide", gone);
    return () => {
      gone();
      window.removeEventListener("pagehide", gone);
      opened.close();
      channel.current = null;
    };
  }, [paperId]);

  const latestReader = reader ?? [...readers.values()].at(-1) ?? null;
  const versionId = latestReader?.versionId ?? route.versionId ?? paper.current_version.version_id;
  const pageIndex = latestReader?.pageIndex ?? route.page - 1;
  const hiddenSessions = latestReader ? new Set(latestReader.hiddenSessions) : ownHidden;
  const connected = latestReader !== null;

  /** 원문 탭이 있으면 그 탭이 그곳을 열고, 없으면 그곳을 새 탭의 Reader로 연다 */
  const show = (message: Parameters<ChatChannel["post"]>[0], place: Partial<Extract<Route, { kind: "reader" }>>) => {
    if (connected) {
      channel.current?.post(message);
      return;
    }
    const target = { kind: "reader", paperId, versionId, anchorId: null, page: null, blockId: null, session: null, ...place } as const;
    window.open(formatRoute(target), "_blank");
  };
  const showCitation = (citation: Citation) =>
    show({ type: "show-citation", citation }, citation.block_id ? { page: citation.page_index + 1, blockId: citation.block_id } : { anchorId: citation.anchor_id });

  if (returned) {
    return (
      <p className="status chat-tab-returned" role="status">
        대화를 원문 탭의 사이드바로 되돌렸습니다. 이 탭은 닫아도 됩니다.
      </p>
    );
  }
  return (
    <div className="chat-tab">
      <header className="chat-tab-head">
        <span className="chat-tab-paper" title={paper.title}>
          {paper.title}
        </span>
        {connected ? (
          <>
            <span className="chat-tab-link muted" role="status">
              원문 탭과 이어짐 · p.{pageIndex + 1}
            </span>
            <button type="button" className="btn btn-ghost" onClick={returnToSidebar}>
              사이드바로 되돌리기
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={() => show({ type: "show-page", pageNumber: pageIndex + 1 }, { page: pageIndex + 1 })}>
            원문 열기
          </button>
        )}
      </header>
      <div className={artifact ? "chat-tab-body has-artifact" : "chat-tab-body"}>
        <ChatPanel
          paperId={paperId}
          versionId={versionId}
          pageIndex={pageIndex}
          bridge={bridge}
          request={request}
          visible
          hiddenSessions={hiddenSessions}
          onShowCitation={showCitation}
          onShowAnchor={(anchorId) => show({ type: "show-anchor", anchorId }, { anchorId })}
          onShowPage={(pageNumber) => show({ type: "show-page", pageNumber }, { page: pageNumber })}
          onOpenArtifact={(opened) => setArtifact({ artifact: opened, nonce: Date.now() })}
          onDiscarded={(answer) => channel.current?.post({ type: "discarded", answer })}
          onSessionRenamed={(sessionId, title) => channel.current?.post({ type: "renamed", sessionId, title })}
          onSessionDeleted={(sessionId) => channel.current?.post({ type: "deleted", sessionId })}
        />
        {artifact && <ArtifactWindow key={artifact.nonce} artifact={artifact.artifact} versionId={versionId} onClose={() => setArtifact(null)} />}
      </div>
    </div>
  );
}
