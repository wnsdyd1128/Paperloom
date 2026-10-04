/**
 * 서재 표 (U6, 시안 Library): 제목 · 본문 추출 · 주석 · 대화 · 태그 · 마지막 열람. 최근에 연 논문이 먼저다(서버 차례).
 * 태그 칩을 누르면 그 태그로 거르고, 머리의 태그 메뉴로 여러 태그(하나라도/모두)나 태그 없음을 고른다.
 * 머리의 제목 검색 결과(hits)가 있으면 그 논문만 보이고 찾은 낱말을 표시한다. 모든 상태에서 원본은 읽을 수 있다 (IMPL §5.2).
 */
import { useState } from "react";

import type { SnippetPart } from "../search/api";
import type { Paper, SourceVersion } from "./api";
import { TagEditor, TagFilterMenu } from "./TagMenus";
import { matchesTags, NO_TAG_FILTER, type TagFilter, tagCounts } from "./tagFilter";
import type { Library } from "./useLibrary";

// 상태는 본문 검색이 되는지를 말한다 (IMPL §5.2).
const STATUS_LABELS: Record<SourceVersion["status"], string> = {
  READY_TO_READ: "본문 추출 대기",
  PARSING: "본문 추출 중",
  INDEXED: "검색 가능",
  PARTIAL: "일부 쪽만 검색 가능",
  FAILED: "검색 불가",
};
const STATUS_TONES: Record<SourceVersion["status"], string> = {
  READY_TO_READ: "tag-outline",
  PARSING: "tag-outline",
  INDEXED: "tag-neutral",
  PARTIAL: "tag-accent",
  FAILED: "tag-accent",
};
const REASON_LABELS: Record<string, string> = {
  NO_TEXT_LAYER: "글자 층 없음(스캔·이미지)",
  RESOURCE_LIMIT: "처리 한도 초과",
  PARSER_ERROR: "추출 오류",
  PASSWORD_REQUIRED: "암호 필요",
  MALFORMED_PDF: "손상된 PDF",
};

type Props = Readonly<{
  library: Library;
  /** 머리의 제목 검색 결과(논문 → 찾은 낱말을 표시한 제목). 검색하지 않았으면 null */
  hits: ReadonlyMap<string, readonly SnippetPart[]> | null;
  onOpen: (paper: Paper) => void;
}>;

export function LibraryPage({ library, hits, onOpen }: Props) {
  const [filter, setFilter] = useState<TagFilter>(NO_TAG_FILTER);
  const { list, papers } = library;
  const counts = tagCounts(papers);
  const searched = hits ? papers.filter((paper) => hits.has(paper.paper_id)) : papers;
  const shown = searched.filter((paper) => matchesTags(paper, filter));
  const filtering = filter.untagged || filter.tags.length > 0;
  const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();
  // 태그 이름을 바꾸면 고른 거르기도 새 이름으로(이미 고른 태그로 합쳤으면 하나로), 지우면 거르기에서 뺀다
  const renameTag = async (name: string, next: string) => {
    if (!(await library.renameTag(name, next))) return;
    setFilter((current) => {
      const tags = current.tags.map((tag) => (same(tag, name) ? next : tag));
      return { ...current, tags: tags.filter((tag, index) => tags.findIndex((other) => same(other, tag)) === index) };
    });
  };
  const deleteTag = async (name: string) => {
    if (await library.deleteTag(name)) setFilter((current) => ({ ...current, tags: current.tags.filter((tag) => !same(tag, name)) }));
  };
  const toggleTag = (name: string) => {
    const chosen = filter.tags.some((tag) => tag.toLowerCase() === name.toLowerCase());
    setFilter({ ...filter, untagged: false, tags: chosen ? filter.tags.filter((tag) => tag.toLowerCase() !== name.toLowerCase()) : [...filter.tags, name] });
  };

  return (
    <section className="shelf" aria-labelledby="library-heading">
      <div className="shelf-head">
        <div className="shelf-title">
          <h2 id="library-heading">서재</h2>
          <span className="shelf-count" data-testid="shelf-count">
            {filtering || hits ? `${shown.length} / ${papers.length}편` : `${papers.length}편`}
          </span>
        </div>
        {/* 끌어 놓기는 화면 어디에나 된다(LibraryShell). 한도는 서버 UploadLimits (IMPL §5.1) */}
        <div className="drop-hint" aria-hidden="true">
          PDF를 끌어다 놓기 <span className="muted">100 MiB · 300쪽</span>
        </div>
      </div>
      {filtering && (
        <div className="filter-chips" role="group" aria-label="태그 거르기">
          <span className="muted">필터 · {filter.untagged ? "태그 없음" : filter.mode === "all" ? "모두 포함" : "하나라도"}</span>
          {filter.untagged ? (
            <button type="button" className="filter-chip" aria-label="태그 없음 거르기 빼기" onClick={() => setFilter({ ...filter, untagged: false })}>
              태그 없음 ×
            </button>
          ) : (
            filter.tags.map((tag) => (
              <button key={tag} type="button" className="filter-chip" aria-label={`${tag} 거르기 빼기`} onClick={() => toggleTag(tag)}>
                {tag} ×
              </button>
            ))
          )}
          <button type="button" className="btn btn-ghost" onClick={() => setFilter({ ...filter, tags: [], untagged: false })}>
            모두 지우기
          </button>
        </div>
      )}
      {list.kind === "loading" && <p className="muted">목록을 불러오는 중…</p>}
      {list.kind === "failed" && <p className="status error">목록을 불러오지 못했습니다. 백엔드(이 PC의 Paperloom 서버)가 실행 중인지 확인하세요.</p>}
      {list.kind === "ready" && papers.length === 0 && <p className="muted">아직 등록된 논문이 없습니다. PDF를 등록하거나 끌어다 놓으세요.</p>}
      {list.kind === "ready" && papers.length > 0 && (
        <table className="table shelf-table">
          <thead>
            <tr>
              <th scope="col">제목</th>
              <th scope="col" className="col-status">
                본문 추출
              </th>
              <th scope="col" className="col-count">
                주석
              </th>
              <th scope="col" className="col-count">
                대화
              </th>
              <th scope="col" className="col-tags">
                <TagFilterMenu
                  filter={filter}
                  counts={counts}
                  untaggedCount={papers.filter((paper) => paper.tags.length === 0).length}
                  onChange={setFilter}
                  onRename={(name, next) => void renameTag(name, next)}
                  onDelete={(name) => void deleteTag(name)}
                />
              </th>
              <th scope="col" className="col-opened">
                마지막 열람
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((paper) => (
              <PaperRow
                key={paper.paper_id}
                paper={paper}
                title={hits?.get(paper.paper_id) ?? null}
                filter={filter}
                known={counts.map((item) => item.name)}
                onOpen={onOpen}
                onRetry={(item) => void library.retry(item)}
                onToggleTag={toggleTag}
                onSetTags={(item, tags) => void library.setTags(item, tags)}
              />
            ))}
          </tbody>
        </table>
      )}
      {list.kind === "ready" && papers.length > 0 && shown.length === 0 && filtering && (
        <p className="muted shelf-empty">
          {filter.untagged
            ? "태그가 없는 논문이 없습니다."
            : filter.mode === "all"
              ? "고른 태그를 모두 가진 논문이 없습니다. \"하나라도\"로 바꾸거나 태그를 줄여 보세요."
              : "고른 태그가 붙은 논문이 없습니다."}
        </p>
      )}
    </section>
  );
}

type RowProps = Readonly<{
  paper: Paper;
  /** 제목 검색에서 찾은 낱말을 표시한 제목 */
  title: readonly SnippetPart[] | null;
  filter: TagFilter;
  known: readonly string[];
  onOpen: (paper: Paper) => void;
  onRetry: (paper: Paper) => void;
  onToggleTag: (name: string) => void;
  onSetTags: (paper: Paper, tags: readonly string[]) => void;
}>;

function PaperRow({ paper, title, filter, known, onOpen, onRetry, onToggleTag, onSetTags }: RowProps) {
  const version = paper.current_version;
  const chosen = (name: string) => filter.tags.some((tag) => tag.toLowerCase() === name.toLowerCase());
  return (
    <tr data-paper-id={paper.paper_id}>
      <td className="shelf-title-cell">
        <button type="button" className="link-button paper-open" onClick={() => onOpen(paper)} title={paper.title}>
          {title ? title.map((part, index) => (part.match ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>)) : paper.title}
        </button>
      </td>
      <td data-status={version.status}>
        <span className={`tag ${STATUS_TONES[version.status]}`}>
          {STATUS_LABELS[version.status] ?? version.status}
          {version.status_reason && ` · ${REASON_LABELS[version.status_reason] ?? version.status_reason}`}
        </span>
        {(version.status === "FAILED" || version.status === "PARTIAL") && (
          <button type="button" className="link-button retry-parse" onClick={() => onRetry(paper)}>
            다시 추출
          </button>
        )}
      </td>
      <td className="num">{paper.annotation_count || "—"}</td>
      <td className="num">{paper.conversation_count || "—"}</td>
      <td>
        <div className="tag-cell">
          {paper.tags.map((tag) => (
            <button key={tag} type="button" className={chosen(tag) ? "tag-chip is-on" : "tag-chip"} aria-pressed={chosen(tag)} title={`${tag}로 거르기`} onClick={() => onToggleTag(tag)}>
              {tag}
            </button>
          ))}
          <TagEditor title={paper.title} tags={paper.tags} known={known} onChange={(tags) => onSetTags(paper, tags)} />
        </div>
      </td>
      <td className="num muted">{paper.last_opened_at ? new Date(paper.last_opened_at).toLocaleDateString("ko-KR") : "—"}</td>
    </tr>
  );
}
