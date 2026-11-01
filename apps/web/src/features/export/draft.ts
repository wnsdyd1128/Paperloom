/** 내보내기 창에서 고른 것 (기능 명세 F-02·F-03·F-10). 창 안의 상태일 뿐 저장하지 않는다. 화면 없이 시험하도록 순수 함수만 둔다. */

import type { BundleRequest, OutboxStatus, PageRange, TextMode, WikiOutbox } from "./api";

export const MAX_PAPERS = 20;
export const MAX_ANCHORS = 200;
export const MAX_TITLE_CHARS = 500;
export const MAX_CONTENT_CHARS = 200_000;
const MAX_RANGES = 20;

export type ProposalDraft = Readonly<{ key: number; title: string; content: string; anchorIds: readonly string[] }>;

export type PaperDraft = Readonly<{
  anchorIds: readonly string[];
  includeComments: boolean;
  includeRegionImages: boolean;
  textMode: TextMode;
  /** 화면의 쪽 범위 글, 예: 1-5, 8 */
  pageRanges: string;
  answerIds: readonly string[];
  proposals: readonly ProposalDraft[];
}>;

export const EMPTY_DRAFT: PaperDraft = {
  anchorIds: [],
  includeComments: true,
  includeRegionImages: false,
  textMode: "none", // LLM Wiki 수신기가 texts/를 받기 전까지 기본은 싣지 않음이다
  pageRanges: "",
  answerIds: [],
  proposals: [],
};

export type DraftEntry = Readonly<{ versionId: string; pageCount: number; draft: PaperDraft }>;
export type DraftProblems = Readonly<{ anchors: boolean; ranges: boolean; titles: readonly number[]; contents: readonly number[] }>;

export function toggled(list: readonly string[], id: string): readonly string[] {
  return list.includes(id) ? list.filter((item) => item !== id) : [...list, id];
}

/** 제안의 근거를 체크한다. 고르지 않은 위치를 체크하면 F-02에서도 고른 상태가 된다 */
export function toggleProposalAnchor(draft: PaperDraft, key: number, anchorId: string): PaperDraft {
  const proposal = draft.proposals.find((item) => item.key === key);
  if (!proposal) return draft;
  const adding = !proposal.anchorIds.includes(anchorId);
  return {
    ...draft,
    anchorIds: adding && !draft.anchorIds.includes(anchorId) ? [...draft.anchorIds, anchorId] : draft.anchorIds,
    proposals: draft.proposals.map((item) => (item.key === key ? { ...item, anchorIds: toggled(item.anchorIds, anchorId) } : item)),
  };
}

/** "1-5, 8"을 0부터 세는 범위로 바꾼다. 형식이 틀리거나 쪽 밖이면 null */
export function parsePageRanges(text: string, pageCount: number): readonly PageRange[] | null {
  const parts = text.split(",").map((part) => part.trim());
  if (parts.length > MAX_RANGES) return null;
  const ranges: PageRange[] = [];
  for (const part of parts) {
    const match = /^(\d+)(?:\s*-\s*(\d+))?$/.exec(part);
    if (!match) return null;
    const first = Number(match[1]);
    const last = match[2] === undefined ? first : Number(match[2]);
    if (first < 1 || first > last || last > pageCount) return null;
    ranges.push({ from: first - 1, to: last - 1 });
  }
  return ranges;
}

export function findProblems(draft: PaperDraft, pageCount: number): DraftProblems {
  return {
    anchors: draft.anchorIds.length > MAX_ANCHORS,
    ranges: draft.textMode === "ranges" && parsePageRanges(draft.pageRanges, pageCount) === null,
    titles: draft.proposals.filter((item) => !item.title.trim()).map((item) => item.key),
    contents: draft.proposals.filter((item) => !item.content.trim()).map((item) => item.key),
  };
}

export function hasProblems(problems: DraftProblems): boolean {
  return problems.anchors || problems.ranges || problems.titles.length > 0 || problems.contents.length > 0;
}

export function toRequest(entries: readonly DraftEntry[]): BundleRequest {
  return {
    papers: entries.map(({ versionId, pageCount, draft }) => ({
      version_id: versionId,
      anchor_ids: draft.anchorIds,
      include_comments: draft.includeComments,
      include_region_images: draft.includeRegionImages,
      text: draft.textMode === "ranges" ? { mode: "ranges", ranges: parsePageRanges(draft.pageRanges, pageCount) ?? [] } : { mode: draft.textMode },
    })),
    answer_ids: entries.flatMap(({ draft }) => draft.answerIds),
    proposals: entries.flatMap(({ versionId, draft }) =>
      draft.proposals.map((item) => ({ version_id: versionId, title: item.title.trim(), content_markdown: item.content, anchor_ids: item.anchorIds })),
    ),
  };
}

/** 제안 본문에 붙일 답변 글: 지금 글 뒤에 빈 줄을 두고 잇는다 */
export function withAnswers(content: string, answers: readonly string[]): string {
  return [content.trimEnd(), ...answers].filter(Boolean).join("\n\n");
}

const OUTBOX_PROBLEMS: Readonly<Record<Exclude<OutboxStatus, "ready">, string>> = {
  not_configured: "Wiki로 보낼 폴더가 없습니다. 설정의 wiki.outbox_path와 그 폴더를 확인하세요.",
  unwritable: "Wiki로 보낼 폴더에 쓸 수 없습니다. 폴더 권한을 확인하세요.",
};

/** 내보내기를 막는 이유. 막지 않으면 null (F-08) */
export function outboxProblem(outbox: WikiOutbox): string | null {
  return outbox.status === "ready" ? null : OUTBOX_PROBLEMS[outbox.status];
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}
