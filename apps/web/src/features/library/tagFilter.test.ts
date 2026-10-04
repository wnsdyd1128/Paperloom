import { describe, expect, it } from "vitest";

import { matchesTags, type TagFilter, tagCounts } from "./tagFilter";

const papers = [
  { paper_id: "a", tags: ["Cache Modeling", "Scheduling"] },
  { paper_id: "b", tags: ["Cache Modeling"] },
  { paper_id: "c", tags: ["VLN"] },
  { paper_id: "d", tags: [] },
];
const shown = (filter: TagFilter) => papers.filter((paper) => matchesTags(paper, filter)).map((paper) => paper.paper_id);

describe("matchesTags (U6 태그 거르기)", () => {
  it("고른 태그가 없으면 모두", () => {
    expect(shown({ tags: [], mode: "any", untagged: false })).toEqual(["a", "b", "c", "d"]);
  });

  it("하나라도: 고른 태그 가운데 하나라도 있으면", () => {
    expect(shown({ tags: ["Scheduling", "VLN"], mode: "any", untagged: false })).toEqual(["a", "c"]);
  });

  it("모두 포함: 고른 태그가 다 있어야", () => {
    expect(shown({ tags: ["Cache Modeling", "Scheduling"], mode: "all", untagged: false })).toEqual(["a"]);
    expect(shown({ tags: ["Scheduling", "VLN"], mode: "all", untagged: false })).toEqual([]);
  });

  it("태그 없음: 태그가 하나도 없는 논문만(고른 태그는 보지 않는다)", () => {
    expect(shown({ tags: ["VLN"], mode: "any", untagged: true })).toEqual(["d"]);
  });

  it("대소문자는 가리지 않는다", () => {
    expect(shown({ tags: ["cache modeling"], mode: "any", untagged: false })).toEqual(["a", "b"]);
  });
});

describe("tagCounts", () => {
  it("태그마다 논문 수, 이름 차례", () => {
    expect(tagCounts(papers)).toEqual([
      { name: "Cache Modeling", count: 2 },
      { name: "Scheduling", count: 1 },
      { name: "VLN", count: 1 },
    ]);
  });
});
