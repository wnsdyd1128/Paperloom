/**
 * 서재·답변 화면의 틀 (U6, 시안 Library): 머리(로고, 서재/답변/설정, Claude Code 상태, 제목 검색, PDF 등록)와
 * 화면 어디에나 PDF를 끌어다 놓는 받침. 제목 검색은 서재 표를 거르고 찾은 낱말을 표시한다(D1: 검색 패널을 뺐다).
 */
import "./library.css";

import { type FormEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../../shared/http";
import { Icon } from "../../shared/Icon";
import type { Citation } from "../answers/api";
import { ConversationsPage } from "../answers/ConversationsPage";
import { bridgeState, useBridge } from "../chat/BridgeStatus";
import { search, type SnippetPart } from "../search/api";
import { SettingsDialog } from "../settings/SettingsDialog";
import type { Conversation } from "../threads/api";
import type { Paper } from "./api";
import { LibraryPage } from "./LibraryPage";
import { useLibrary } from "./useLibrary";

type Search =
  | Readonly<{ kind: "idle" }>
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "ready"; hits: ReadonlyMap<string, readonly SnippetPart[]> }>
  | Readonly<{ kind: "failed"; message: string }>;

type Props = Readonly<{
  view: "library" | "answers";
  onView: (view: "library" | "answers") => void;
  onOpenPaper: (paper: Paper) => void;
  onOpenConversation: (conversation: Conversation) => void;
  onOpenCitation: (citation: Citation) => void;
}>;

export function LibraryShell({ view, onView, onOpenPaper, onOpenConversation, onOpenCitation }: Props) {
  const library = useLibrary();
  const bridge = useBridge();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Search>({ kind: "idle" });
  const dragging = useFileDrop((files) => void library.upload(files));
  const fileInput = useRef<HTMLInputElement>(null);
  const state = bridgeState(bridge);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      setFound({ kind: "idle" });
      return;
    }
    onView("library");
    setFound({ kind: "loading" });
    try {
      const result = await search(query);
      setFound({ kind: "ready", hits: new Map(result.papers.map((hit) => [hit.paper_id, hit.title])) });
    } catch (error) {
      const message =
        error instanceof ApiError && error.body.code === "INVALID_QUERY" ? error.message : "검색하지 못했습니다. 백엔드 연결을 확인하세요.";
      setFound({ kind: "failed", message });
    }
  }

  function clearSearch() {
    setQuery("");
    setFound({ kind: "idle" });
  }

  return (
    <div className="library-shell">
      <header className="library-head">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <h1 className="brand-name">Paperloom</h1>
        </span>
        <nav className="library-nav" aria-label="화면">
          <button type="button" aria-current={view === "library" ? "page" : undefined} onClick={() => onView("library")}>
            서재
          </button>
          <button type="button" aria-current={view === "answers" ? "page" : undefined} onClick={() => onView("answers")}>
            답변
          </button>
          <button type="button" aria-haspopup="dialog" onClick={() => setSettingsOpen(true)}>
            설정
          </button>
        </nav>
        <div className="library-head-right">
          {/* 색만으로 구분하지 않도록 상태를 글로도 쓴다 (IMPL §10.4). 누르면 설정의 연결 상태와 켜는 명령을 본다 */}
          <button
            type="button"
            className="bridge-indicator"
            data-state={state}
            title={state === "offline" ? "Claude Code 브리지가 꺼져 있습니다. 누르면 켜는 방법을 봅니다." : "Claude Code (이 PC, 구독 사용량)"}
            onClick={() => setSettingsOpen(true)}
          >
            <span className="bridge-dot" aria-hidden="true" />
            Claude Code{state === "offline" ? " 꺼짐" : state === "checking" ? " 확인 중" : " (이 PC)"}
          </button>
          <form role="search" className="title-search" onSubmit={(event) => void onSearch(event)}>
            <Icon name="search" size={15} />
            <input
              type="search"
              aria-label="제목 검색어"
              placeholder="논문 제목 검색"
              title="제목의 낱말 (앞부분만 써도 됩니다). Enter로 찾습니다"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                if (!event.target.value) setFound({ kind: "idle" });
              }}
            />
          </form>
          <button type="button" className="btn btn-primary upload-button" disabled={library.uploading} onClick={() => fileInput.current?.click()}>
            <Icon name="upload" size={15} />
            PDF 등록
          </button>
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            hidden
            aria-label="PDF 파일"
            onChange={(event) => {
              const files = [...(event.target.files ?? [])];
              event.target.value = ""; // 같은 파일을 다시 고를 수 있게
              if (files.length > 0) void library.upload(files);
            }}
          />
        </div>
      </header>
      <div className="library-notices">
        {view === "library" && <SearchStatus found={found} onClear={clearSearch} />}
        {library.notice && (
          <p className={`status ${library.notice.tone}`} role="status">
            {library.notice.text}
          </p>
        )}
      </div>
      <main className="library-main">
        {view === "library" ? (
          <LibraryPage library={library} hits={found.kind === "ready" ? found.hits : null} onOpen={onOpenPaper} />
        ) : (
          <ConversationsPage onOpen={onOpenConversation} onOpenCitation={onOpenCitation} />
        )}
      </main>
      {dragging && (
        <div className="drop-overlay" aria-hidden="true">
          <p>PDF를 놓으면 서재에 등록합니다</p>
        </div>
      )}
      {settingsOpen && <SettingsDialog bridge={bridge} onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}

function SearchStatus({ found, onClear }: Readonly<{ found: Search; onClear: () => void }>) {
  if (found.kind === "idle") return null;
  if (found.kind === "loading") return <p className="status pending">찾는 중…</p>;
  if (found.kind === "failed") {
    return (
      <p className="status error" role="status">
        {found.message}
      </p>
    );
  }
  return (
    <p className="search-status" role="status">
      {found.hits.size === 0 ? "제목에서 찾은 논문이 없습니다. 모든 낱말이 제목에 있어야 합니다." : `제목에서 ${found.hits.size}편을 찾았습니다.`}
      <button type="button" className="btn btn-ghost" onClick={onClear}>
        검색 지우기
      </button>
    </p>
  );
}

/** 창 어디에나 파일을 끌어다 놓으면 받는다. 파일을 끄는 동안 true. 글이나 링크를 끄는 것은 무시한다. */
function useFileDrop(onFiles: (files: File[]) => void): boolean {
  const [dragging, setDragging] = useState(false);
  const onFilesRef = useRef(onFiles);
  onFilesRef.current = onFiles;

  useEffect(() => {
    let depth = 0; // dragenter·dragleave는 자식 요소마다 온다
    const hasFiles = (event: DragEvent) => event.dataTransfer?.types.includes("Files") ?? false;
    const onEnter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth++;
      setDragging(true);
    };
    const onLeave = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const onOver = (event: DragEvent) => {
      if (hasFiles(event)) event.preventDefault(); // 놓기를 받는다(브라우저가 PDF를 열지 않게)
    };
    const onDrop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth = 0;
      setDragging(false);
      onFilesRef.current([...(event.dataTransfer?.files ?? [])]);
    };
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("dragover", onOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("drop", onDrop);
    };
  }, []);
  return dragging;
}
