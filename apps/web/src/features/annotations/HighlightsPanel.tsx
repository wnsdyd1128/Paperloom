import { type MouseEvent, useState } from "react";

import { Icon } from "../../shared/Icon";
import { relativeTime } from "../../shared/time";
import { usePreferences } from "../settings/PreferencesProvider";
import type { Annotation, HighlightColor } from "./api";
import { filterHighlights, HIGHLIGHT_COLOR_LABELS, HIGHLIGHT_COLORS, highlightsMarkdown } from "./highlights";
import { describeFailure } from "./NotesPanel";
import { QuoteView } from "./QuoteView";
import type { AnnotationsState } from "./useAnnotations";

type Props = Readonly<{
  state: AnnotationsState;
  focusedAnchorId: string | null;
  /** 원문 복귀 링크 (버전 고정 주소, IMPL §4.3) */
  anchorHref: (anchorId: string) => string;
  onOpen: (annotation: Annotation) => void;
  onRecolor: (annotation: Annotation, color: HighlightColor) => Promise<void>;
  onRemove: (annotation: Annotation) => Promise<void>;
}>;

/**
 * 사이드바 "하이라이트" (U5, 시안 Reader v3 하이라이트 패널). 색이 있는 주석을 쪽 순서로 보이고, 색으로 거르고
 * 인용·메모로 찾는다. 누르면 원문 위치로 가고, 색을 바꾸거나 지운다. "모두 복사"는 보이는 하이라이트를 Markdown 목록으로
 * 복사한다. 메모 고치기는 주석 패널에서 한다(같은 주석이 메모가 있으면 거기에도 보인다).
 */
export function HighlightsPanel({ state, focusedAnchorId, anchorHref, onOpen, onRecolor, onRemove }: Props) {
  const [colors, setColors] = useState<ReadonlySet<HighlightColor>>(() => new Set(HIGHLIGHT_COLORS));
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const { preferences } = usePreferences();
  const items = state.kind === "ready" ? state.items : [];
  const all = filterHighlights(items, new Set(HIGHLIGHT_COLORS), "");
  const shown = filterHighlights(items, colors, query);

  function toggle(color: HighlightColor) {
    setColors((current) => {
      const next = new Set(current);
      if (next.has(color)) next.delete(color);
      else next.add(color);
      return next;
    });
  }

  async function copyAll() {
    await navigator.clipboard?.writeText(highlightsMarkdown(shown, preferences.math_delimiters));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <section className="side-section" aria-labelledby="highlights-heading">
      <header className="side-head">
        <h2 id="highlights-heading" className="side-title">
          하이라이트
        </h2>
        <button type="button" className="btn btn-icon side-tool" aria-label="모두 복사" title={copied ? "복사했습니다" : "모두 복사"} disabled={shown.length === 0} onClick={() => void copyAll()}>
          <Icon name={copied ? "check" : "copy"} size={15} />
        </button>
      </header>
      <div className="side-filters">
        <div className="color-filter" role="group" aria-label="색으로 거르기">
          <span>색으로 거르기</span>
          {HIGHLIGHT_COLORS.map((color) => (
            <button
              key={color}
              type="button"
              className="color-swatch"
              data-color={color}
              aria-pressed={colors.has(color)}
              aria-label={HIGHLIGHT_COLOR_LABELS[color]}
              title={HIGHLIGHT_COLOR_LABELS[color]}
              onClick={() => toggle(color)}
            >
              {colors.has(color) && <Icon name="check" size={12} />}
            </button>
          ))}
        </div>
        <label className="input side-search">
          <Icon name="search" size={14} />
          <input type="search" aria-label="하이라이트 검색" placeholder="하이라이트 검색" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
      </div>
      {state.kind === "loading" && <p className="side-empty muted">하이라이트를 불러오는 중…</p>}
      {state.kind === "failed" && <p className="side-empty status error">하이라이트를 불러오지 못했습니다.</p>}
      {state.kind === "ready" && all.length === 0 && <p className="side-empty muted">하이라이트가 없습니다. 글을 고르고 하이라이트(H)를 누르세요.</p>}
      {state.kind === "ready" && all.length > 0 && shown.length === 0 && <p className="side-empty muted">맞는 하이라이트가 없습니다.</p>}
      <ol className="annotation-list note-list highlight-list">
        {shown.map((annotation) => (
          <HighlightItem
            key={annotation.annotation_id}
            annotation={annotation}
            focused={annotation.anchor.anchor_id === focusedAnchorId}
            href={anchorHref(annotation.anchor.anchor_id)}
            onOpen={onOpen}
            onRecolor={onRecolor}
            onRemove={onRemove}
          />
        ))}
      </ol>
    </section>
  );
}

type ItemProps = Readonly<{
  annotation: Annotation;
  focused: boolean;
  href: string;
  onOpen: Props["onOpen"];
  onRecolor: Props["onRecolor"];
  onRemove: Props["onRemove"];
}>;

function HighlightItem({ annotation, focused, href, onOpen, onRecolor, onRemove }: ItemProps) {
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

  async function remove() {
    if (!window.confirm(annotation.comment ? "이 하이라이트를 지울까요? 메모도 함께 지워집니다." : "이 하이라이트를 지울까요?")) return;
    await run(() => onRemove(annotation));
  }

  return (
    <li
      className={focused ? "annotation note-item is-focused" : "annotation note-item"}
      data-annotation-id={annotation.annotation_id}
      data-color={annotation.color}
      data-revision={annotation.revision}
    >
      <a className="note-page" href={href} onClick={openLink} aria-current={focused ? "location" : undefined} aria-label={`p.${anchor.page_index + 1} 원문 위치`}>
        p.{anchor.page_index + 1}
      </a>
      <div className="note-main">
        <div className="highlight-quote" data-color={annotation.color}>
          <QuoteView quote={anchor.quote} displayQuote={anchor.display_quote} />
        </div>
        {annotation.comment && <p className="comment">{annotation.comment}</p>}
        <span className="note-meta">
          {relativeTime(annotation.created_at)}
          <span className="color-choices" role="group" aria-label="색 바꾸기">
            {HIGHLIGHT_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                className="color-swatch is-small"
                data-color={color}
                aria-pressed={annotation.color === color}
                aria-label={`${HIGHLIGHT_COLOR_LABELS[color]}으로`}
                title={HIGHLIGHT_COLOR_LABELS[color]}
                disabled={busy}
                onClick={() => annotation.color !== color && void run(() => onRecolor(annotation, color))}
              />
            ))}
          </span>
        </span>
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
