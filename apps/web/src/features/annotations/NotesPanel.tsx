import { type FormEvent, type MouseEvent, useState } from "react";

import { Icon } from "../../shared/Icon";
import { ApiError } from "../../shared/http";
import { relativeTime } from "../../shared/time";
import { usePreferences } from "../settings/PreferencesProvider";
import { type Annotation, anchorImageUrl, REGION_KIND_LABELS, REGION_KINDS, type RegionKind } from "./api";
import { copiedQuote } from "./highlights";
import { QuoteView } from "./QuoteView";
import type { AnnotationsState } from "./useAnnotations";

type Filter = "all" | "text" | "region";

type Props = Readonly<{
  state: AnnotationsState;
  focusedAnchorId: string | null;
  /** 원문 복귀 링크 (버전 고정 주소, IMPL §4.3) */
  anchorHref: (anchorId: string) => string;
  onOpen: (annotation: Annotation) => void;
  onUpdate: (annotation: Annotation, comment: string) => Promise<void>;
  /** 영역의 종류만 바꾼다 (IMPL §10.6). */
  onChangeKind: (annotation: Annotation, kind: RegionKind) => Promise<void>;
  onRemove: (annotation: Annotation) => Promise<void>;
}>;

/**
 * 사이드바 "주석" (시안 3k). 이 버전의 주석을 쪽 순서로 보이고, 전체·텍스트·그림으로 거르고 인용·메모로 찾는다.
 * 누르면 원문 위치로 가고, 메모를 고치거나 지운다. "모두 복사"는 보이는 주석을 Markdown 목록으로 복사한다.
 */
export function NotesPanel({ state, focusedAnchorId, anchorHref, onOpen, onUpdate, onChangeKind, onRemove }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const { preferences } = usePreferences();
  const items = state.kind === "ready" ? state.items : [];
  const counts = { all: items.length, text: items.filter(isText).length, region: items.filter((item) => !isText(item)).length };
  const needle = query.trim().toLowerCase();
  const shown = items.filter(
    (item) =>
      (filter === "all" || (filter === "text") === isText(item)) &&
      (!needle || `${item.anchor.quote} ${item.anchor.display_quote ?? ""} ${item.comment}`.toLowerCase().includes(needle)),
  );

  async function copyAll() {
    const lines = shown.map((item) => {
      const quote = isText(item) ? `“${copiedQuote(item.anchor, preferences.math_delimiters)}”` : `[${REGION_KIND_LABELS[item.anchor.kind as RegionKind]}]`;
      return `- p.${item.anchor.page_index + 1} ${quote}${item.comment ? ` — ${item.comment}` : ""}`;
    });
    await navigator.clipboard?.writeText(lines.join("\n"));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <section className="side-section" aria-labelledby="annotations-heading">
      <header className="side-head">
        <h2 id="annotations-heading" className="side-title">
          주석
        </h2>
        <button type="button" className="btn btn-icon side-tool" aria-label="모두 복사" title={copied ? "복사했습니다" : "모두 복사"} disabled={shown.length === 0} onClick={() => void copyAll()}>
          <Icon name={copied ? "check" : "copy"} size={15} />
        </button>
      </header>
      <div className="side-filters">
        <div className="seg" role="radiogroup" aria-label="주석 거르기">
          {(["all", "text", "region"] as const).map((value) => (
            <label key={value} className="seg-opt">
              <input type="radio" name="notes-filter" checked={filter === value} onChange={() => setFilter(value)} />
              {FILTER_LABELS[value]} {counts[value]}
            </label>
          ))}
        </div>
        <label className="input side-search">
          <Icon name="search" size={14} />
          <input type="search" aria-label="주석 검색" placeholder="주석 검색" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
      </div>
      {state.kind === "loading" && <p className="side-empty muted">주석을 불러오는 중…</p>}
      {state.kind === "failed" && <p className="side-empty status error">주석을 불러오지 못했습니다.</p>}
      {state.kind === "ready" && items.length === 0 && <p className="side-empty muted">저장한 주석이 없습니다.</p>}
      {state.kind === "ready" && items.length > 0 && shown.length === 0 && <p className="side-empty muted">맞는 주석이 없습니다.</p>}
      <ol className="annotation-list note-list">
        {shown.map((annotation) => (
          <NoteItem
            key={annotation.annotation_id}
            annotation={annotation}
            focused={annotation.anchor.anchor_id === focusedAnchorId}
            href={anchorHref(annotation.anchor.anchor_id)}
            onOpen={onOpen}
            onUpdate={onUpdate}
            onChangeKind={onChangeKind}
            onRemove={onRemove}
          />
        ))}
      </ol>
    </section>
  );
}

const FILTER_LABELS: Readonly<Record<Filter, string>> = { all: "전체", text: "텍스트", region: "그림" };

function isText(annotation: Annotation): boolean {
  return annotation.anchor.kind === "text";
}

type ItemProps = Readonly<{
  annotation: Annotation;
  focused: boolean;
  href: string;
  onOpen: Props["onOpen"];
  onUpdate: Props["onUpdate"];
  onChangeKind: Props["onChangeKind"];
  onRemove: Props["onRemove"];
}>;

function NoteItem({ annotation, focused, href, onOpen, onUpdate, onChangeKind, onRemove }: ItemProps) {
  const [draft, setDraft] = useState<string | null>(null); // null이면 보기 상태
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { anchor } = annotation;

  function openLink(event: MouseEvent) {
    // 새 탭·창으로 여는 조작은 브라우저에 맡긴다.
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onOpen(annotation);
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (failure) {
      setError(describeFailure(failure));
    } finally {
      setBusy(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (draft === null) return;
    await run(async () => {
      await onUpdate(annotation, draft);
      setDraft(null);
    });
  }

  async function remove() {
    if (!window.confirm("이 주석을 지울까요? 강조 표시도 사라집니다.")) return;
    await run(() => onRemove(annotation));
  }

  const meta = [
    relativeTime(annotation.created_at),
    isText(annotation) ? "텍스트" : REGION_KIND_LABELS[anchor.kind as RegionKind],
    anchor.display_quote && "추정 표기 있음",
  ].filter(Boolean);
  return (
    <li
      className={focused ? "annotation note-item is-focused" : "annotation note-item"}
      data-annotation-id={annotation.annotation_id}
      data-anchor-id={anchor.anchor_id}
      data-revision={annotation.revision}
    >
      <a className="note-page" href={href} onClick={openLink} aria-current={focused ? "location" : undefined} aria-label={`p.${anchor.page_index + 1} 원문 위치`}>
        p.{anchor.page_index + 1}
      </a>
      <div className="note-main">
        {isText(annotation) ? (
          <QuoteView quote={anchor.quote} displayQuote={anchor.display_quote} />
        ) : (
          <div className="region-preview">
            <img src={anchorImageUrl(anchor.anchor_id, 1)} alt={`${REGION_KIND_LABELS[anchor.kind as RegionKind]} 영역, ${anchor.page_index + 1}쪽`} loading="lazy" />
            <select
              aria-label="영역 종류"
              className="note-kind"
              value={anchor.kind}
              onChange={(event) => void run(() => onChangeKind(annotation, event.target.value as RegionKind))}
              disabled={busy}
            >
              {REGION_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {REGION_KIND_LABELS[kind]}
                </option>
              ))}
            </select>
          </div>
        )}
        {draft === null ? (
          <>
            {annotation.comment && <p className="comment">{annotation.comment}</p>}
            <span className="note-meta">
              {meta.join(" · ")}
              <button type="button" className="btn btn-ghost note-edit" onClick={() => setDraft(annotation.comment)} disabled={busy}>
                메모 수정
              </button>
            </span>
          </>
        ) : (
          <form className="comment-form" onSubmit={(event) => void save(event)}>
            <textarea className="input" aria-label="메모 수정" value={draft} onChange={(event) => setDraft(event.target.value)} rows={3} />
            <div className="annotation-actions">
              <button type="submit" className="btn btn-primary" disabled={busy}>
                수정 저장
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setDraft(null)} disabled={busy}>
                취소
              </button>
            </div>
          </form>
        )}
        {error && (
          <p className="status error" role="alert">
            {error}
          </p>
        )}
      </div>
      <button type="button" className="btn btn-icon note-remove" aria-label="삭제" title="삭제" onClick={() => void remove()} disabled={busy}>
        <Icon name="trash" size={14} />
      </button>
    </li>
  );
}

/** 저장·삭제 실패의 까닭 (하이라이트 패널도 쓴다). */
export function describeFailure(failure: unknown): string {
  if (!(failure instanceof ApiError)) return "저장하지 못했습니다. 백엔드 연결을 확인하세요.";
  if (failure.body.code === "REVISION_CONFLICT") {
    return "그사이 다른 곳에서 이 주석이 바뀌어 최신 내용을 다시 불러왔습니다. 확인한 뒤 다시 저장하세요.";
  }
  return failure.message;
}
