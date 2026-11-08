import { type KeyboardEvent, useEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";
import { AnswerMarkdown } from "../answers/AnswerMarkdown";
import { type Artifact, ARTIFACT_LABELS, artifactFileName, artifactMimeType } from "./artifact";
import { isFramed, previewDocument } from "./preview";
import "./artifacts.css";

type Preview = Readonly<{ kind: "loading" }> | Readonly<{ kind: "ready"; html: string }> | Readonly<{ kind: "failed"; message: string }>;

/**
 * Reader 본문 위에 넓게 띄우는 아티팩트 창 (2026-11-08 사용자 요청·결정: 본문 위 큰 창, 스크립트는 격리해서 실행).
 * HTML·SVG·Mermaid·React는 격리 iframe(frameDocument.ts)에서, 문서는 답과 같은 Markdown으로, 코드는 글자 그대로 보인다.
 * 미리 보기와 코드를 오가고, 코드를 복사하거나 파일로 내려받는다. Esc나 닫기 단추로 닫으면 읽던 자리가 그대로다.
 * 다른 아티팩트를 열면 창을 새로 만든다(부르는 쪽이 key를 바꾼다).
 */
export function ArtifactWindow({ artifact, onClose }: Readonly<{ artifact: Artifact; onClose: () => void }>) {
  const hasPreview = artifact.type !== "code";
  const [view, setView] = useState<"preview" | "code">(hasPreview ? "preview" : "code");
  const [preview, setPreview] = useState<Preview>({ kind: "loading" });
  const [copied, setCopied] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => closeRef.current?.focus(), []);

  useEffect(() => {
    if (!isFramed(artifact)) return;
    let cancelled = false;
    previewDocument(artifact).then(
      (html) => !cancelled && setPreview({ kind: "ready", html }),
      (error: unknown) => !cancelled && setPreview({ kind: "failed", message: error instanceof Error ? error.message : String(error) }),
    );
    return () => {
      cancelled = true;
    };
  }, [artifact]);

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "Escape") return;
    event.stopPropagation(); // 본문 선택 지우기 등 Reader의 Esc로 가지 않는다
    onClose();
  };

  const copy = () =>
    void navigator.clipboard?.writeText(artifact.content).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });

  const download = () => {
    const url = URL.createObjectURL(new Blob([artifact.content], { type: artifactMimeType(artifact) }));
    const link = document.createElement("a");
    link.href = url;
    link.download = artifactFileName(artifact);
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <section className="artifact-window" role="dialog" aria-label={`아티팩트: ${artifact.title}`} onKeyDown={onKeyDown}>
      <header className="artifact-head">
        <Icon name="fileText" size={16} />
        <h2 className="artifact-title" title={artifact.title}>
          {artifact.title}
        </h2>
        <span className="tag tag-neutral">{ARTIFACT_LABELS[artifact.type] + (artifact.language ? ` · ${artifact.language}` : "")}</span>
        {hasPreview && (
          <span className="artifact-views" role="group" aria-label="보기">
            <button type="button" className="btn" aria-pressed={view === "preview"} onClick={() => setView("preview")}>
              미리 보기
            </button>
            <button type="button" className="btn" aria-pressed={view === "code"} onClick={() => setView("code")}>
              코드
            </button>
          </span>
        )}
        <span className="artifact-copied" role="status">
          {copied ? "복사했습니다" : ""}
        </span>
        <button type="button" className="btn btn-icon" aria-label="코드 복사" title="코드 복사" onClick={copy}>
          <Icon name="copy" size={16} />
        </button>
        <button type="button" className="btn btn-icon" aria-label="파일로 내려받기" title={`${artifactFileName(artifact)}로 내려받기`} onClick={download}>
          <Icon name="download" size={16} />
        </button>
        <button ref={closeRef} type="button" className="btn btn-icon" aria-label="아티팩트 닫기" title="닫기 (Esc)" onClick={onClose}>
          <Icon name="x" size={16} />
        </button>
      </header>
      <div className="artifact-body">
        {view === "code" ? (
          <pre className="artifact-code">
            <code>{artifact.content}</code>
          </pre>
        ) : artifact.type === "markdown" ? (
          <div className="artifact-doc">
            <AnswerMarkdown markdown={artifact.content} canCite={() => false} onCite={() => undefined} />
          </div>
        ) : preview.kind === "loading" ? (
          <p className="artifact-status muted">미리 보기를 준비하는 중…</p>
        ) : preview.kind === "failed" ? (
          <p className="artifact-status status error">{preview.message}</p>
        ) : (
          <ArtifactFrame html={preview.html} title={artifact.title} />
        )}
      </div>
    </section>
  );
}

/**
 * 격리 iframe. sandbox는 allow-scripts뿐이라 출처 없는 문서로 돈다(frameDocument.ts). 문서가 스스로 다른 주소로
 * 옮겨 가면(두 번째 load) 그 화면을 치운다. 이동 요청 자체는 막지 못한다.
 */
function ArtifactFrame({ html, title }: Readonly<{ html: string; title: string }>) {
  const loads = useRef(0);
  const [moved, setMoved] = useState(false);
  if (moved) {
    return <p className="artifact-status status error">아티팩트가 다른 주소로 이동하려 해서 화면을 치웠습니다. 코드 보기에서 내용을 확인하세요.</p>;
  }
  return (
    <iframe
      className="artifact-frame"
      title={`${title} 미리 보기`}
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      srcDoc={html}
      onLoad={() => {
        loads.current += 1;
        if (loads.current > 1) setMoved(true);
      }}
    />
  );
}
