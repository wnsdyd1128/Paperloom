import { describe, expect, it } from "vitest";

import {
  EMPTY_DRAFT,
  findProblems,
  formatBytes,
  hasArtifact,
  hasProblems,
  outboxProblem,
  parsePageRanges,
  type PaperDraft,
  toggled,
  toggledArtifact,
  toggleProposalAnchor,
  toRequest,
  withAnswers,
} from "./draft";

const proposal = (key: number, fields: Partial<PaperDraft["proposals"][number]> = {}) => ({ key, title: "제목", content: "본문", anchorIds: [], ...fields });

describe("쪽 범위 글", () => {
  it("화면은 1부터, API는 0부터다", () => {
    expect(parsePageRanges("1-5, 8", 10)).toEqual([{ from: 0, to: 4 }, { from: 7, to: 7 }]);
    expect(parsePageRanges(" 3 - 3 ", 3)).toEqual([{ from: 2, to: 2 }]);
  });

  it.each(["", "a", "1-", "0", "5-2", "11", "1-11", "1,,2", "-1"])("틀린 글은 고르지 않는다: %j", (text) => {
    expect(parsePageRanges(text, 10)).toBeNull();
  });

  it("범위는 20개까지다", () => {
    expect(parsePageRanges(Array(20).fill("1").join(","), 10)).toHaveLength(20);
    expect(parsePageRanges(Array(21).fill("1").join(","), 10)).toBeNull();
  });
});

describe("고르기", () => {
  it("넣고 뺀다", () => {
    expect(toggled(["a"], "b")).toEqual(["a", "b"]);
    expect(toggled(["a", "b"], "a")).toEqual(["b"]);
  });

  it("아티팩트는 답변과 차례로 가린다. 목록의 다른 칸은 넣지 않는다", () => {
    const listed = { answer_id: "x", index: 1, title: "그림", content: "<svg/>" };
    const chosen = toggledArtifact([{ answer_id: "x", index: 0 }], listed);
    expect(chosen).toEqual([
      { answer_id: "x", index: 0 },
      { answer_id: "x", index: 1 },
    ]);
    expect(hasArtifact(chosen, { answer_id: "x", index: 1 })).toBe(true);
    expect(hasArtifact(chosen, { answer_id: "y", index: 1 })).toBe(false);
    expect(toggledArtifact(chosen, listed)).toEqual([{ answer_id: "x", index: 0 }]);
  });

  it("제안의 근거를 체크하면 고른 위치에도 들어가고, 빼도 고른 위치는 남는다", () => {
    const draft = { ...EMPTY_DRAFT, proposals: [proposal(1)] };
    const linked = toggleProposalAnchor(draft, 1, "a");
    expect(linked.anchorIds).toEqual(["a"]);
    expect(linked.proposals[0].anchorIds).toEqual(["a"]);

    const unlinked = toggleProposalAnchor(linked, 1, "a");
    expect(unlinked.anchorIds).toEqual(["a"]);
    expect(unlinked.proposals[0].anchorIds).toEqual([]);
  });

  it("이미 고른 위치를 두 번 넣지 않는다", () => {
    const draft = { ...EMPTY_DRAFT, anchorIds: ["a"], proposals: [proposal(1)] };
    expect(toggleProposalAnchor(draft, 1, "a").anchorIds).toEqual(["a"]);
  });
});

describe("미리보기 전 검사", () => {
  it("빈 제목·본문과 틀린 쪽 범위를 짚는다", () => {
    const draft = { ...EMPTY_DRAFT, textMode: "ranges", pageRanges: "9", proposals: [proposal(1, { title: "  " }), proposal(2, { content: "\n" }), proposal(3)] } as const;
    const problems = findProblems(draft, 3);
    expect(problems).toEqual({ anchors: false, ranges: true, titles: [1], contents: [2] });
    expect(hasProblems(problems)).toBe(true);
  });

  it("위치는 논문마다 200개까지다", () => {
    const ids = (count: number) => Array.from({ length: count }, (_, index) => `a${index}`);
    expect(hasProblems(findProblems({ ...EMPTY_DRAFT, anchorIds: ids(200) }, 3))).toBe(false);
    expect(findProblems({ ...EMPTY_DRAFT, anchorIds: ids(201) }, 3).anchors).toBe(true);
  });

  it("문제가 없으면 넘어간다. 쪽 범위는 고를 때만 본다", () => {
    expect(hasProblems(findProblems({ ...EMPTY_DRAFT, pageRanges: "x", proposals: [proposal(1)] }, 3))).toBe(false);
  });
});

describe("요청", () => {
  it("판본마다 고른 것을 모으고 기본값을 보낸다", () => {
    const first = { ...EMPTY_DRAFT, anchorIds: ["a"], answerIds: ["x"], proposals: [proposal(1, { title: " 제목 ", anchorIds: ["a"] })] };
    const second = { ...EMPTY_DRAFT, includeComments: false, includeRegionImages: true, textMode: "ranges", pageRanges: "2-3", answerIds: ["y"], artifacts: [{ answer_id: "y", index: 2 }] } as const;

    expect(toRequest([{ versionId: "v1", pageCount: 5, draft: first }, { versionId: "v2", pageCount: 5, draft: second }])).toEqual({
      papers: [
        { version_id: "v1", anchor_ids: ["a"], include_comments: true, include_region_images: false, text: { mode: "anchor_pages" } },
        { version_id: "v2", anchor_ids: [], include_comments: false, include_region_images: true, text: { mode: "ranges", ranges: [{ from: 1, to: 2 }] } },
      ],
      answer_ids: ["x", "y"],
      artifacts: [{ answer_id: "y", index: 2 }],
      proposals: [{ version_id: "v1", title: "제목", content_markdown: "본문", anchor_ids: ["a"] }],
    });
  });
});

describe("표시", () => {
  it("답변 글을 빈 줄을 두고 잇는다", () => {
    expect(withAnswers("", ["가", "나"])).toBe("가\n\n나");
    expect(withAnswers("앞\n", ["가"])).toBe("앞\n\n가");
  });

  it("outbox가 준비되지 않은 이유를 말한다", () => {
    expect(outboxProblem({ status: "ready", path: "/data/outbox" })).toBeNull();
    expect(outboxProblem({ status: "not_configured", path: null })).toContain("wiki.outbox_path");
    expect(outboxProblem({ status: "unwritable", path: "/data/outbox" })).toContain("권한");
  });

  it("크기", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KiB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MiB");
  });
});
