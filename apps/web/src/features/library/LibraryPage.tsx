/**
 * 서재 표 (U6, 시안 Library): 고르기 · 제목 · 본문 추출 · 주석 · 대화 · 태그 · 마지막 열람 · 삭제. 최근에 연 논문이 먼저다(서버 차례).
 * 제목 칸에는 첫 쪽 썸네일과 저자·연도·쪽 수 한 줄을 함께 두어 논문을 알아보게 한다(2026-11-25 사용자 결정).
 * 고른 논문은 머리의 "Wiki로 내보내기"로 한 번에 내보낸다(20편까지, 각 논문의 지금 판본).
 * 삭제(2026-10-05 사용자 요청)는 한 편씩, 확인 창에서 함께 지워지는 기록을 알린 뒤 바로 완전히 지운다.
 * 태그 칩을 누르면 그 태그로 거르고, 머리의 태그 메뉴로 여러 태그(하나라도/모두)나 태그 없음을 고른다.
 * 머리의 제목 검색 결과(hits)가 있으면 그 논문만 보이고 찾은 낱말을 표시한다. 모든 상태에서 원본은 읽을 수 있다 (IMPL §5.2).
 * 거르고 찾은 논문은 페이지로 나눠 보이고, 표 아래에서 페이지를 옮기거나 페이지당 편 수를 고른다(2026-11-25 사용자 요청).
 */
import { type ReactNode, useEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";
import { formatTime, relativeTime } from "../../shared/time";
import { MAX_PAPERS } from "../export/draft";
import type { SnippetPart } from "../search/api";
import { firstPageThumbnailUrl, type Paper, type SourceVersion } from "./api";
import { clampPage, pageAfterResize, pageSlice, rememberPageSize, storedPageSize } from "./pagination";
import { paperMeta } from "./paperMeta";
import { ShelfPager } from "./ShelfPager";
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
  UNREADABLE_TEXT: "글자를 읽을 수 없음(글꼴에 문자 정보 없음)",
  RESOURCE_LIMIT: "처리 한도 초과",
  PARSER_ERROR: "추출 오류",
  PASSWORD_REQUIRED: "암호 필요",
  MALFORMED_PDF: "손상된 PDF",
  UNMAPPED_CHARS: "일부 기호를 읽지 못함",
};

/** 기호 일부(수식 등)만 읽지 못한 PARTIAL은 모든 쪽을 검색할 수 있다(2026-10-14 사용자 논문). 이유를 뒤에 붙인다. */
function statusLabel(version: SourceVersion): string {
  if (version.status === "PARTIAL" && version.status_reason === "UNMAPPED_CHARS") return STATUS_LABELS.INDEXED;
  return STATUS_LABELS[version.status] ?? version.status;
}

type Props = Readonly<{
  library: Library;
  /** 머리의 제목 검색 결과(논문 → 찾은 낱말을 표시한 제목). 검색하지 않았으면 null */
  hits: ReadonlyMap<string, readonly SnippetPart[]> | null;
  /** Wiki로 내보내기 단추와 논문 고르기 칸을 보일지 (설정 wiki.enabled, 개발 중이라 기본으로 숨긴다) */
  wikiExport: boolean;
  /** Wiki로 내보내기를 막는 이유. 막지 않으면 null */
  exportProblem: string | null;
  /** 서재가 비었을 때(첫 올리기 결과를 보여 주는 동안 포함) 표 대신 놓는 PDF 받침. 없으면 null */
  dropZone: ReactNode;
  onOpen: (paper: Paper) => void;
  onExport: (papers: readonly Paper[]) => void;
}>;

export function LibraryPage({ library, hits, wikiExport, exportProblem, dropZone, onOpen, onExport }: Props) {
  const [filter, setFilter] = useState<TagFilter>(NO_TAG_FILTER);
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const { list, papers } = library;
  const chosenPapers = papers.filter((paper) => chosen.has(paper.paper_id)); // 지운 논문은 저절로 빠진다
  const toggleChosen = (paper: Paper) => {
    const next = new Set(chosen);
    if (!next.delete(paper.paper_id)) next.add(paper.paper_id);
    setChosen(next);
  };
  const exportBlocked =
    exportProblem ?? (chosenPapers.length === 0 ? "내보낼 논문을 고르세요." : chosenPapers.length > MAX_PAPERS ? `한 번에 ${MAX_PAPERS}편까지 내보낼 수 있습니다. 지금 ${chosenPapers.length}편을 골랐습니다.` : null);
  const counts = tagCounts(papers);
  const searched = hits ? papers.filter((paper) => hits.has(paper.paper_id)) : papers;
  const shown = searched.filter((paper) => matchesTags(paper, filter));
  const filtering = filter.untagged || filter.tags.length > 0;
  // 페이지: 거르기·검색이 바뀌면 첫 페이지로 돌아가고, 논문을 지워 페이지가 줄면 마지막 페이지를 보인다(clampPage)
  const [pageSize, setPageSize] = useState(storedPageSize);
  const [page, setPage] = useState(1);
  const section = useRef<HTMLElement>(null);
  useEffect(() => setPage(1), [hits, filter]);
  const currentPage = clampPage(page, shown.length, pageSize);
  const visible = pageSlice(shown, currentPage, pageSize);
  const goToPage = (next: number) => {
    setPage(next);
    section.current?.closest(".library-main")?.scrollTo({ top: 0 }); // 새 페이지는 맨 위부터 본다
  };
  const changePageSize = (next: number) => {
    setPage(pageAfterResize(currentPage, pageSize, next));
    setPageSize(next);
    rememberPageSize(next);
  };
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
    <section className="shelf" aria-labelledby="library-heading" ref={section}>
      <div className="shelf-head">
        <div className="shelf-title">
          <h2 id="library-heading">서재</h2>
          <span className="shelf-count" data-testid="shelf-count">
            {filtering || hits ? `${shown.length} / ${papers.length}편` : `${papers.length}편`}
          </span>
        </div>
        <div className="shelf-tools">
          {wikiExport && (
            <button type="button" className="btn btn-secondary" disabled={exportBlocked !== null} title={exportBlocked ?? undefined} onClick={() => onExport(chosenPapers)}>
              <Icon name="send" size={15} />
              Wiki로 내보내기{chosenPapers.length > 0 && ` (${chosenPapers.length}편)`}
            </button>
          )}
          {/* 끌어 놓기는 화면 어디에나 된다(LibraryShell). 한도는 서버 UploadLimits (IMPL §5.1) */}
          <div className="drop-hint" aria-hidden="true">
            PDF를 끌어다 놓기 <span className="muted">100 MiB · 300쪽</span>
          </div>
        </div>
      </div>
      {wikiExport && chosenPapers.length > MAX_PAPERS && (
        <p className="status error" role="status">
          {exportBlocked}
        </p>
      )}
      {filtering && (
        <div className="filter-chips" role="group" aria-label="태그 거르기">
          <span className="muted">필터 · {filter.untagged ? "태그 없음" : filter.mode === "all" ? "모두 포함" : "하나라도"}</span>
          {filter.untagged ? (
            <button type="button" className="filter-chip" aria-label="태그 없음 거르기 빼기" onClick={() => setFilter({ ...filter, untagged: false })}>
              태그 없음
              <Icon name="x" size={11} />
            </button>
          ) : (
            filter.tags.map((tag) => (
              <button key={tag} type="button" className="filter-chip" aria-label={`${tag} 거르기 빼기`} onClick={() => toggleTag(tag)}>
                {tag}
                <Icon name="x" size={11} />
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
      {list.kind === "ready" && dropZone && (
        <div className="shelf-drop">
          {papers.length === 0 && <p className="muted">아직 등록된 논문이 없습니다.</p>}
          {dropZone}
        </div>
      )}
      {list.kind === "ready" && !dropZone && papers.length > 0 && (
        <table className="table shelf-table">
          <thead>
            <tr>
              {wikiExport && (
                <th scope="col" className="col-choose">
                  <span className="sr-only">내보낼 논문 고르기</span>
                </th>
              )}
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
              <th scope="col" className="col-actions">
                <span className="sr-only">삭제</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((paper) => (
              <PaperRow
                key={paper.paper_id}
                paper={paper}
                title={hits?.get(paper.paper_id) ?? null}
                filter={filter}
                known={counts.map((item) => item.name)}
                chosen={chosen.has(paper.paper_id)}
                onChoose={wikiExport ? toggleChosen : null}
                onOpen={onOpen}
                onRetry={(item) => void library.retry(item)}
                onToggleTag={toggleTag}
                onSetTags={(item, tags) => void library.setTags(item, tags)}
                onDelete={(item) => void library.removePaper(item)}
              />
            ))}
          </tbody>
        </table>
      )}
      {list.kind === "ready" && !dropZone && shown.length > 0 && (
        <ShelfPager total={shown.length} page={currentPage} size={pageSize} onPage={goToPage} onSize={changePageSize} />
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
  /** 내보내려고 골랐는지 */
  chosen: boolean;
  /** Wiki로 내보내기가 꺼져 있으면 null이고 고르기 칸이 없다 */
  onChoose: ((paper: Paper) => void) | null;
  onOpen: (paper: Paper) => void;
  onRetry: (paper: Paper) => void;
  onToggleTag: (name: string) => void;
  onSetTags: (paper: Paper, tags: readonly string[]) => void;
  onDelete: (paper: Paper) => void;
}>;

/** 지우기 전에 묻는 말. 함께 지워지는 기록을 알린다 */
function deleteQuestion(paper: Paper): string {
  const counts = [paper.annotation_count && `주석 ${paper.annotation_count}개`, paper.conversation_count && `대화 ${paper.conversation_count}개`].filter(Boolean);
  const records = ["원본 PDF와 본문", ...counts, "하이라이트·쪽 번역"].join(", ");
  return `"${paper.title}" 논문을 지울까요?\n\n${records}이 모두 지워지며 되돌릴 수 없습니다.`;
}

/**
 * 첫 쪽 썸네일. 눌러도 논문이 열리지만 이름과 키보드 조작은 곁의 제목 단추가 맡으므로 화면 낭독기에서 숨긴다.
 * 쪽을 그리지 못하면(암호·손상된 PDF) 아래의 문서 아이콘만 남는다. 끌 수 없게 둔다: 그림을 끌면 브라우저가
 * 파일을 끄는 것으로 알려 PDF 받침이 뜬다.
 */
function PaperThumb({ versionId, onOpen }: Readonly<{ versionId: string; onOpen: () => void }>) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false); // 다 받은 뒤에 서서히 드러낸다(아이콘에서 그림으로 툭 바뀌지 않게)
  return (
    <span className="paper-thumb" aria-hidden="true" onClick={onOpen}>
      <Icon name="fileText" size={18} />
      {!failed && (
        <img
          className={loaded ? "is-loaded" : undefined}
          src={firstPageThumbnailUrl(versionId)}
          alt=""
          loading="lazy"
          decoding="async"
          draggable={false}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
      )}
    </span>
  );
}

function PaperRow({ paper, title, filter, known, chosen, onChoose, onOpen, onRetry, onToggleTag, onSetTags, onDelete }: RowProps) {
  const version = paper.current_version;
  const status = statusLabel(version);
  const reason = version.status_reason ? (REASON_LABELS[version.status_reason] ?? version.status_reason) : null;
  const filtered = (name: string) => filter.tags.some((tag) => tag.toLowerCase() === name.toLowerCase());
  return (
    <tr data-paper-id={paper.paper_id}>
      {onChoose && (
        <td className="shelf-choose">
          <input type="checkbox" aria-label={`${paper.title} 내보내기로 고르기`} checked={chosen} onChange={() => onChoose(paper)} />
        </td>
      )}
      <td className="shelf-title-cell">
        <div className="paper-main">
          <PaperThumb versionId={version.version_id} onOpen={() => onOpen(paper)} />
          <div className="paper-text">
            <button type="button" className="link-button paper-open" onClick={() => onOpen(paper)} title={paper.title}>
              <span className="paper-title">
                {title ? title.map((part, index) => (part.match ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>)) : paper.title}
              </span>
            </button>
            <p className="paper-meta">{paperMeta(paper)}</p>
          </div>
        </div>
      </td>
      {/* 이유는 둘째 줄에 두 줄까지 보인다(전체는 title). 칸의 글은 "상태 · 이유" 그대로다 */}
      <td data-status={version.status} title={reason ? `${status} · ${reason}` : undefined}>
        <span className={`tag ${STATUS_TONES[version.status]}`}>
          {status}
          {reason && (
            <>
              <span className="status-sep"> · </span>
              <span className="status-reason">{reason}</span>
            </>
          )}
        </span>
        {(version.status === "FAILED" || version.status === "PARTIAL") && (
          <button type="button" className="link-button retry-parse" onClick={() => onRetry(paper)}>
            다시 추출
          </button>
        )}
      </td>
      <td className={paper.annotation_count ? "num" : "num is-empty"}>{paper.annotation_count || "—"}</td>
      <td className={paper.conversation_count ? "num" : "num is-empty"}>{paper.conversation_count || "—"}</td>
      <td>
        <div className="tag-cell">
          {paper.tags.map((tag) => (
            <button key={tag} type="button" className={filtered(tag) ? "tag-chip is-on" : "tag-chip"} aria-pressed={filtered(tag)} title={`${tag}로 거르기`} onClick={() => onToggleTag(tag)}>
              {tag}
            </button>
          ))}
          <TagEditor title={paper.title} tags={paper.tags} known={known} onChange={(tags) => onSetTags(paper, tags)} />
        </div>
      </td>
      {/* 답변·주석 목록과 같은 짧은 시각(방금 · 3시간 전 · 어제 · 11월 19일). 정확한 시각은 title */}
      <td className={paper.last_opened_at ? "num muted" : "num muted is-empty"}>
        {paper.last_opened_at ? (
          <time dateTime={paper.last_opened_at} title={formatTime(paper.last_opened_at)}>
            {relativeTime(paper.last_opened_at)}
          </time>
        ) : (
          "—"
        )}
      </td>
      <td className="row-actions">
        <button
          type="button"
          className="btn btn-icon paper-delete"
          aria-label={`${paper.title} 삭제`}
          title="논문 삭제"
          onClick={() => window.confirm(deleteQuestion(paper)) && onDelete(paper)}
        >
          <Icon name="trash" size={14} />
        </button>
      </td>
    </tr>
  );
}
