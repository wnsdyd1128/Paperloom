/**
 * Wiki로 내보내기 창 (기능 명세 F-01–F-05). Reader(지금 논문)와 서재(고른 논문들)에서 같은 창을 연다.
 * 고르기 → 미리보기 → 내보내기 차례다. 미리보기에서 돌아가면 고른 것이 그대로 있고, 선택을 바꾸면 미리보기를 다시 거친다.
 * 고른 것은 이 창 안의 상태일 뿐 저장되지 않는다. Paperloom 쪽 일은 bundle을 쓰는 데서 끝난다.
 */
import "./export.css";

import { useEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";
import type { Paper } from "../library/api";
import { type Bundle, type BundlePreview, type BundleRequest, createBundle, describeError, previewBundle } from "./api";
import { type DraftProblems, EMPTY_DRAFT, findProblems, formatBytes, hasProblems, MAX_ANCHORS, type PaperDraft, toRequest } from "./draft";
import { ExportCard } from "./ExportCard";
import { ExportPreview, overLimit } from "./ExportPreview";
import { useOutbox } from "./useOutbox";

type Step =
  | Readonly<{ kind: "edit" }>
  | Readonly<{ kind: "preview"; request: BundleRequest; preview: BundlePreview }>
  | Readonly<{ kind: "done"; bundle: Bundle }>;

type Props = Readonly<{
  papers: readonly Paper[];
  onClose: () => void;
  /** 내보낸 bundle 기록 화면으로 */
  onShowHistory: () => void;
}>;

export function ExportDialog({ papers, onClose, onShowHistory }: Props) {
  const { outbox, problem } = useOutbox();
  const [listed, setListed] = useState(papers);
  const [drafts, setDrafts] = useState<ReadonlyMap<string, PaperDraft>>(new Map());
  const [step, setStep] = useState<Step>({ kind: "edit" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [marking, setMarking] = useState(false); // 미리보기를 누른 뒤에만 빈 칸을 표시한다
  const ref = useRef<HTMLDivElement>(null);

  const draftOf = (paper: Paper) => drafts.get(paper.current_version.version_id) ?? EMPTY_DRAFT;
  const hasWriting = [...drafts.values()].some((draft) => draft.proposals.some((item) => item.title || item.content));
  // 쓴 제안은 저장되지 않으므로 실수로 닫아 잃지 않게 묻는다
  const close = () => (step.kind === "done" || !hasWriting || window.confirm("쓴 제안을 버리고 닫을까요?")) && onClose();
  const closeRef = useRef(close);
  closeRef.current = close;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.isComposing) closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, []);

  function problemsOf(paper: Paper): DraftProblems {
    return findProblems(draftOf(paper), paper.current_version.page_count);
  }

  async function run<T>(work: () => Promise<T>, done: (result: T) => void) {
    setBusy(true);
    setError(null);
    try {
      done(await work());
    } catch (failure) {
      setError(describeError(failure));
    } finally {
      setBusy(false);
    }
  }

  function showPreview() {
    setMarking(true);
    if (listed.some((paper) => hasProblems(problemsOf(paper)))) {
      setError(`표시한 칸을 고치세요: 위치는 논문마다 ${MAX_ANCHORS}개까지이고, 제안의 제목·본문은 비울 수 없고, 쪽 범위는 논문 안이어야 합니다.`);
      return;
    }
    const request = toRequest(listed.map((paper) => ({ versionId: paper.current_version.version_id, pageCount: paper.current_version.page_count, draft: draftOf(paper) })));
    void run(
      () => previewBundle(request),
      (preview) => setStep({ kind: "preview", request, preview }),
    );
  }

  return (
    <div className="export-backdrop">
      <div className="export-dialog" role="dialog" aria-modal="true" aria-labelledby="export-title" tabIndex={-1} ref={ref}>
        <header className="export-head">
          <h2 id="export-title">Wiki로 내보내기</h2>
          <span className="muted export-outbox" data-status={outbox?.status}>
            {outbox?.status === "ready" ? `보낼 폴더 ${outbox.path}` : problem}
          </span>
          <button type="button" className="btn btn-icon" aria-label="내보내기 닫기" title="닫기 (Esc)" onClick={close}>
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="export-body">
          {error && (
            <p className="status error" role="alert">
              {error}
            </p>
          )}
          {step.kind === "edit" &&
            listed.map((paper) => (
              <ExportCard
                key={paper.paper_id}
                paper={paper}
                draft={draftOf(paper)}
                problems={marking ? problemsOf(paper) : null}
                onChange={(draft) => setDrafts(new Map(drafts).set(paper.current_version.version_id, draft))}
                onRemove={() => setListed(listed.filter((item) => item !== paper))}
              />
            ))}
          {step.kind === "edit" && listed.length === 0 && <p className="muted">내보낼 논문이 없습니다. 창을 닫고 다시 고르세요.</p>}
          {step.kind === "preview" && <ExportPreview preview={step.preview} />}
          {step.kind === "done" && <Done bundle={step.bundle} onShowHistory={onShowHistory} />}
        </div>
        <footer className="export-foot">
          {step.kind === "edit" && (
            <>
              <button type="button" className="btn btn-secondary" onClick={close}>
                취소
              </button>
              <button type="button" className="btn btn-primary" disabled={busy || problem !== null || listed.length === 0} title={problem ?? undefined} onClick={showPreview}>
                {busy ? "계산하는 중…" : "미리보기"}
              </button>
            </>
          )}
          {step.kind === "preview" && (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => {
                  setError(null);
                  setStep({ kind: "edit" });
                }}
              >
                돌아가기
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || overLimit(step.preview)}
                onClick={() => void run(() => createBundle(step.request), (bundle) => setStep({ kind: "done", bundle }))}
              >
                {busy ? "쓰는 중…" : "내보내기"}
              </button>
            </>
          )}
          {step.kind === "done" && (
            <button type="button" className="btn btn-primary" onClick={onClose}>
              닫기
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

function Done({ bundle, onShowHistory }: Readonly<{ bundle: Bundle; onShowHistory: () => void }>) {
  return (
    <div className="export-done" role="status">
      <p>
        Wiki로 내보냈습니다 · bundle <code>{bundle.bundle_id.slice(0, 8)}</code> · 파일 {bundle.file_count}개 · {formatBytes(bundle.size_bytes)}
      </p>
      <p className="muted">LLM Wiki의 'Paperloom 수신'에서 받을 수 있습니다.</p>
      <button type="button" className="btn btn-ghost" onClick={onShowHistory}>
        기록 보기
      </button>
    </div>
  );
}
