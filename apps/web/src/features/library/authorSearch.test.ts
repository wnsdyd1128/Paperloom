import { describe, expect, it } from "vitest";

import { markName, queryWords, searchAuthors } from "./authorSearch";

const paper = (id: string, authors: string[]) => ({ paper_id: id, authors });

describe("queryWords", () => {
  it("빈칸으로 나누고 소문자로 맞춘다. 글자가 없으면 빈 목록이다", () => {
    expect(queryWords("  Jun   XIAO ")).toEqual(["jun", "xiao"]);
    expect(queryWords("   ")).toEqual([]);
  });
});

describe("markName", () => {
  it("이름의 어느 자리든 찾고 찾은 곳을 표시한다(대소문자 무시)", () => {
    expect(markName("Ashish Vaswani", ["vas"])).toEqual([
      { text: "Ashish ", match: false },
      { text: "Vas", match: true },
      { text: "wani", match: false },
    ]);
    expect(markName("박준용", ["준용"])).toEqual([
      { text: "박", match: false },
      { text: "준용", match: true },
    ]);
  });

  it("모든 낱말이 있어야 하고, 낱말의 차례는 상관없다", () => {
    expect(markName("Jun Xiao", ["xiao", "jun"])).toEqual([
      { text: "Jun", match: true },
      { text: " ", match: false },
      { text: "Xiao", match: true },
    ]);
    expect(markName("Jun Xiao", ["jun", "park"])).toBeNull();
  });

  it("겹치는 낱말은 한 번만 표시한다", () => {
    expect(markName("Vaswani", ["vas", "vaswa"])).toEqual([
      { text: "Vaswa", match: true },
      { text: "ni", match: false },
    ]);
  });
});

describe("searchAuthors", () => {
  const papers = [
    paper("a", ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"]),
    paper("b", ["Jun Xiao", "Andy D. Pimentel"]),
    paper("c", []),
  ];

  it("저자가 맞는 논문만 주고, 처음 맞은 저자와 다른 저자 수를 알린다", () => {
    const hits = searchAuthors(papers, "shaz");
    expect([...hits.keys()]).toEqual(["a"]);
    expect(hits.get("a")).toEqual({
      name: [
        { text: "Noam ", match: false },
        { text: "Shaz", match: true },
        { text: "eer", match: false },
      ],
      others: 2,
    });
  });

  it("낱말은 한 저자의 이름에 모두 있어야 한다(저자 둘에 나뉘어 있으면 찾지 않는다)", () => {
    expect([...searchAuthors(papers, "jun xiao").keys()]).toEqual(["b"]);
    expect(searchAuthors(papers, "jun andy").size).toBe(0);
  });

  it("검색어에 글자가 없으면 아무것도 찾지 않는다", () => {
    expect(searchAuthors(papers, "  ").size).toBe(0);
  });
});
