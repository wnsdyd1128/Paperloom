/**
 * 내보내기 창의 판본 한 칸 (기능 명세 F-02·F-03·F-10): 넣을 위치, 메모·이미지·추출문, 답변, Wiki 제안.
 * 처음에는 아무것도 고르지 않는다. 판본을 섞지 않는다: 위치·답변·제안은 그 판본 카드에만 있다.
 */
import { useEffect, useState } from "react";

import { Icon } from "../../shared/Icon";
import { formatTime } from "../../shared/time";
import { type Anchor, listAnnotations, listVersionAnchors, REGION_KIND_LABELS, type RegionKind } from "../annotations/api";
import { type Answer, listAnswers } from "../answers/api";
import { listPageTexts, type Paper } from "../library/api";
import type { TextMode } from "./api";
import { type DraftProblems, MAX_ANCHORS, MAX_CONTENT_CHARS, MAX_TITLE_CHARS, type PaperDraft, toggled, toggleProposalAnchor, withAnswers } from "./draft";

const QUOTE_CHARS = 80;
const QUESTION_CHARS = 80;
const MAX_ANSWERS = 200;
const TEXT_MODES: readonly Readonly<{ value: TextMode; label: string }>[] = [
  { value: "none", label: "싣지 않음" },
  { value: "anchor_pages", label: "고른 위치가 있는 쪽" },
  { value: "all", label: "전체" },
  { value: "ranges", label: "쪽 범위" },
];

type Loaded =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "failed" }>
  | Readonly<{
      kind: "ready";
      anchors: readonly Anchor[];
      memos: ReadonlySet<string>;
      labels: ReadonlyMap<number, string | null>;
      answers: readonly Answer[];
    }>;

type Props = Readonly<{
  paper: Paper;
  draft: PaperDraft;
  problems: DraftProblems | null;
  onChange: (draft: PaperDraft) => void;
  onRemove: () => void;
}>;

export function ExportCard({ paper, draft, problems, onChange, onRemove }: Props) {
  const versionId = paper.current_version.version_id;
  const [loaded, setLoaded] = useState<Loaded>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    Promise.all([listVersionAnchors(versionId), listAnnotations(versionId), listPageTexts(versionId), listAnswers({ paperId: paper.paper_id, origin: "claude_code", limit: MAX_ANSWERS })])
      .then(([anchors, annotations, texts, answers]) => {
        if (cancelled) return;
        const memos = new Set(annotations.filter((item) => item.comment.trim()).map((item) => item.anchor.anchor_id));
        const labels = new Map(texts.pages.map((page) => [page.page_index, page.page_label]));
        setLoaded({ kind: "ready", anchors, memos, labels, answers });
      })
      .catch(() => !cancelled && setLoaded({ kind: "failed" }));
    return () => {
      cancelled = true;
    };
  }, [versionId, paper.paper_id]);

  const facts = [paper.authors.join(", "), paper.year, `판본 ${versionId.slice(0, 8)}`, `${paper.current_version.page_count}쪽`].filter(Boolean);
  return (
    <details className="export-card" open data-version-id={versionId}>
      <summary>
        <span className="export-card-title">
          <b>{paper.title}</b>
          <span className="muted">{facts.join(" · ")}</span>
        </span>
        <button
          type="button"
          className="btn btn-icon"
          aria-label={`${paper.title} 목록에서 빼기`}
          title="목록에서 빼기"
          onClick={(event) => {
            event.preventDefault(); // summary 안의 단추가 칸을 접지 않게
            onRemove();
          }}
        >
          <Icon name="x" size={14} />
        </button>
      </summary>
      {loaded.kind === "loading" && <p className="muted">불러오는 중…</p>}
      {loaded.kind === "failed" && <p className="status error">이 논문의 위치를 불러오지 못했습니다. 백엔드 연결을 확인하세요.</p>}
      {loaded.kind === "ready" && (
        <>
          <AnchorList anchors={loaded.anchors} memos={loaded.memos} labels={loaded.labels} draft={draft} invalid={problems?.anchors ?? false} onChange={onChange} />
          <Options draft={draft} invalid={problems?.ranges ?? false} onChange={onChange} />
          <AnswerList answers={loaded.answers} draft={draft} onChange={onChange} />
          <Proposals anchors={loaded.anchors} labels={loaded.labels} answers={loaded.answers} draft={draft} problems={problems} onChange={onChange} />
        </>
      )}
    </details>
  );
}

function anchorKind(anchor: Anchor): string {
  return anchor.kind === "text" ? "글" : REGION_KIND_LABELS[anchor.kind as RegionKind];
}

function pageName(anchor: Anchor, labels: ReadonlyMap<number, string | null>): string {
  const number = String(anchor.page_index + 1);
  const label = labels.get(anchor.page_index);
  return label && label !== number ? `p.${number} (인쇄 ${label})` : `p.${number}`;
}

function quoteHead(anchor: Anchor): string {
  return (anchor.display_quote ?? anchor.quote).slice(0, QUOTE_CHARS) || "(영역)";
}

type ListProps = Readonly<{
  anchors: readonly Anchor[];
  memos: ReadonlySet<string>;
  labels: ReadonlyMap<number, string | null>;
  draft: PaperDraft;
  invalid: boolean;
  onChange: (draft: PaperDraft) => void;
}>;

function AnchorList({ anchors, memos, labels, draft, invalid, onChange }: ListProps) {
  return (
    <section className="export-section" aria-label="넣을 위치">
      <header className="export-section-head">
        <h4>
          위치 <span className="muted" data-over={invalid || undefined}>{`${draft.anchorIds.length} / ${anchors.length}${invalid ? ` · ${MAX_ANCHORS}개까지 고를 수 있습니다` : ""}`}</span>
        </h4>
        {anchors.length > 0 && (
          <>
            <button type="button" className="btn btn-ghost" onClick={() => onChange({ ...draft, anchorIds: anchors.map((anchor) => anchor.anchor_id) })}>
              모두 고르기
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => onChange({ ...draft, anchorIds: [] })}>
              모두 해제
            </button>
          </>
        )}
      </header>
      {anchors.length === 0 ? (
        <p className="muted">이 논문에 저장된 위치가 없습니다. 위치를 고르지 않아도 논문 정보는 내보낼 수 있습니다.</p>
      ) : (
        <ul className="export-list">
          {anchors.map((anchor) => (
            <li key={anchor.anchor_id}>
              <label className="export-check">
                <input
                  type="checkbox"
                  checked={draft.anchorIds.includes(anchor.anchor_id)}
                  onChange={() => onChange({ ...draft, anchorIds: toggled(draft.anchorIds, anchor.anchor_id) })}
                />
                <span className="tag tag-neutral">{anchorKind(anchor)}</span>
                <span className="export-page">{pageName(anchor, labels)}</span>
                <span className="export-quote">{quoteHead(anchor)}</span>
                {memos.has(anchor.anchor_id) && <span className="tag tag-outline">메모</span>}
              </label>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Options({ draft, invalid, onChange }: Readonly<{ draft: PaperDraft; invalid: boolean; onChange: (draft: PaperDraft) => void }>) {
  return (
    <section className="export-section export-options" aria-label="함께 넣을 것">
      <label className="export-check">
        <input type="checkbox" checked={draft.includeComments} onChange={(event) => onChange({ ...draft, includeComments: event.target.checked })} />
        주석 메모 포함
      </label>
      <label className="export-check">
        <input type="checkbox" checked={draft.includeRegionImages} onChange={(event) => onChange({ ...draft, includeRegionImages: event.target.checked })} />
        영역 이미지 포함
      </label>
      <label className="export-field">
        원문 추출문
        <select className="input" value={draft.textMode} onChange={(event) => onChange({ ...draft, textMode: event.target.value as TextMode })}>
          {TEXT_MODES.map((mode) => (
            <option key={mode.value} value={mode.value}>
              {mode.label}
            </option>
          ))}
        </select>
      </label>
      {draft.textMode === "ranges" && (
        <label className="export-field">
          쪽 범위
          <input
            className="input"
            placeholder="예: 1-5, 8"
            aria-invalid={invalid}
            value={draft.pageRanges}
            onChange={(event) => onChange({ ...draft, pageRanges: event.target.value })}
          />
        </label>
      )}
    </section>
  );
}

function AnswerList({ answers, draft, onChange }: Readonly<{ answers: readonly Answer[]; draft: PaperDraft; onChange: (draft: PaperDraft) => void }>) {
  if (answers.length === 0) return null;
  return (
    <section className="export-section" aria-label="넣을 답변">
      <header className="export-section-head">
        <h4>
          Claude Code 답변 <span className="muted">{`${draft.answerIds.length} / ${answers.length}`}</span>
        </h4>
      </header>
      <ul className="export-list">
        {answers.map((answer) => (
          <li key={answer.answer_id}>
            <label className="export-check">
              <input type="checkbox" checked={draft.answerIds.includes(answer.answer_id)} onChange={() => onChange({ ...draft, answerIds: toggled(draft.answerIds, answer.answer_id) })} />
              <span className="export-quote">{(answer.prompt ?? answer.question).slice(0, QUESTION_CHARS)}</span>
              <span className="muted export-when">
                {formatTime(answer.created_at)} · 근거 {answer.citations.length}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}

type ProposalProps = Readonly<{
  anchors: readonly Anchor[];
  labels: ReadonlyMap<number, string | null>;
  answers: readonly Answer[];
  draft: PaperDraft;
  problems: DraftProblems | null;
  onChange: (draft: PaperDraft) => void;
}>;

function Proposals({ anchors, labels, answers, draft, problems, onChange }: ProposalProps) {
  const update = (key: number, change: Partial<PaperDraft["proposals"][number]>) =>
    onChange({ ...draft, proposals: draft.proposals.map((item) => (item.key === key ? { ...item, ...change } : item)) });
  const chosenAnswers = answers.filter((answer) => draft.answerIds.includes(answer.answer_id)).map((answer) => answer.markdown);
  const add = () => onChange({ ...draft, proposals: [...draft.proposals, { key: Math.max(0, ...draft.proposals.map((item) => item.key)) + 1, title: "", content: "", anchorIds: [] }] });

  return (
    <section className="export-section" aria-label="Wiki 제안">
      <header className="export-section-head">
        <h4>Wiki 제안</h4>
        <button type="button" className="btn btn-ghost" onClick={add}>
          제안 추가
        </button>
      </header>
      {draft.proposals.length === 0 && <p className="muted">제안이 없으면 LLM Wiki는 근거만 보관합니다.</p>}
      {draft.proposals.map((proposal, index) => (
        <fieldset key={proposal.key} className="export-proposal">
          <legend>제안 {index + 1}</legend>
          <label className="export-field">
            제목
            <input
              className="input"
              maxLength={MAX_TITLE_CHARS}
              aria-invalid={problems?.titles.includes(proposal.key) ?? false}
              value={proposal.title}
              onChange={(event) => update(proposal.key, { title: event.target.value })}
            />
          </label>
          <label className="export-field">
            본문 (Markdown)
            <textarea
              className="input"
              rows={6}
              maxLength={MAX_CONTENT_CHARS}
              aria-invalid={problems?.contents.includes(proposal.key) ?? false}
              value={proposal.content}
              onChange={(event) => update(proposal.key, { content: event.target.value })}
            />
          </label>
          <div className="export-proposal-tools">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={chosenAnswers.length === 0}
              title={chosenAnswers.length === 0 ? "위에서 답변을 고르면 그 글을 본문에 넣을 수 있습니다" : undefined}
              onClick={() => update(proposal.key, { content: withAnswers(proposal.content, chosenAnswers) })}
            >
              고른 답변 본문 넣기
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => onChange({ ...draft, proposals: draft.proposals.filter((item) => item.key !== proposal.key) })}>
              제안 빼기
            </button>
          </div>
          {anchors.length > 0 && (
            <div role="group" aria-label={`제안 ${index + 1}의 근거`}>
              <p className="export-subhead">이 제안의 근거</p>
              <ul className="export-list">
                {anchors.map((anchor) => (
                  <li key={anchor.anchor_id}>
                    <label className="export-check">
                      <input type="checkbox" checked={proposal.anchorIds.includes(anchor.anchor_id)} onChange={() => onChange(toggleProposalAnchor(draft, proposal.key, anchor.anchor_id))} />
                      <span className="export-page">{pageName(anchor, labels)}</span>
                      <span className="export-quote">{quoteHead(anchor)}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </fieldset>
      ))}
    </section>
  );
}
