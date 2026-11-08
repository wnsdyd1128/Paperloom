import { useEffect, useState } from "react";

import { Icon } from "../../shared/Icon";
import { relativeTime } from "../../shared/time";
import { type Artifact, ARTIFACT_LABELS } from "./artifact";
import { type ChatArtifact, listChatArtifacts } from "./api";
import "./artifacts.css";

type Listing =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "ready"; artifacts: readonly ChatArtifact[] }>
  | Readonly<{ kind: "failed"; message: string }>;

/**
 * Reader 오른쪽 사이드바의 아티팩트 탭 (2026-11-09 사용자 요청: 대화에서 만든 아티팩트를 모아 두는 보관함).
 * 이 논문의 대화에서 Claude가 만든 아티팩트를 모두 보인다. 아티팩트는 답과 함께 저장되므로 따로 저장하지 않고, 서버가 저장된 답에서
 * 찾는다(GET /api/v1/papers/{paper_id}/artifacts). 답을 버리면 목록에서도 빠진다. 누르면 답의 카드처럼 본문 위 창에서 연다.
 * 탭을 열 때마다 다시 받아 그사이 대화에서 만든 것도 보인다.
 */
export function ArtifactPanel({ paperId, visible, onOpen }: Readonly<{ paperId: string; visible: boolean; onOpen: (artifact: Artifact) => void }>) {
  const [listing, setListing] = useState<Listing>({ kind: "loading" });

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    listChatArtifacts(paperId).then(
      (artifacts) => !cancelled && setListing({ kind: "ready", artifacts }),
      (error: unknown) => !cancelled && setListing({ kind: "failed", message: error instanceof Error ? error.message : String(error) }),
    );
    return () => {
      cancelled = true;
    };
  }, [paperId, visible]);

  return (
    <section className="side-section" aria-labelledby="artifacts-heading">
      <header className="side-head is-strong">
        <h2 id="artifacts-heading" className="side-title">
          아티팩트
        </h2>
        <span className="side-note">누르면 본문 위 창에서 열림</span>
      </header>
      {listing.kind === "loading" ? (
        <p className="side-empty muted">불러오는 중…</p>
      ) : listing.kind === "failed" ? (
        <p className="side-empty status error">아티팩트 목록을 불러오지 못했습니다. {listing.message}</p>
      ) : listing.artifacts.length === 0 ? (
        <p className="side-empty muted">이 논문의 대화에서 Claude가 그림·HTML·문서·코드 같은 아티팩트를 만들면 여기에 모입니다.</p>
      ) : (
        <ol className="artifact-list">
          {listing.artifacts.map((item) => (
            <li key={`${item.answer_id}:${item.index}`}>
              <button type="button" className="artifact-row" onClick={() => onOpen(item)} aria-label={`아티팩트 열기: ${item.title}`}>
                <Icon name="fileText" size={16} />
                <span className="artifact-row-main">
                  <span className="artifact-row-meta">
                    <span className="tag tag-neutral">{ARTIFACT_LABELS[item.type] + (item.language ? ` · ${item.language}` : "")}</span>
                    {relativeTime(item.created_at)}
                  </span>
                  <span className="artifact-row-title">{item.title}</span>
                  {item.prompt && (
                    <span className="artifact-row-prompt" title={item.prompt}>
                      {item.prompt}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
