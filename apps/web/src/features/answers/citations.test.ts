import { describe, expect, it } from "vitest";

import { findCitation, isLegacyAnswer, remarkCitations, remarkInlineMathTags, remarkOutsideEvidence, splitCitations } from "./citations";

describe("splitCitations", () => {
  it("근거 표기 [근거 n]을 링크로 바꾸고 나머지 글은 남긴다", () => {
    expect(splitCitations("앞 [근거 1] 뒤 [근거 2, 3] [근거4, 근거 5].")).toEqual([
      { type: "text", value: "앞 " },
      { type: "link", url: "#cite-1", children: [{ type: "text", value: "근거 1" }] },
      { type: "text", value: " 뒤 " },
      { type: "link", url: "#cite-2", children: [{ type: "text", value: "근거 2" }] },
      { type: "link", url: "#cite-3", children: [{ type: "text", value: "근거 3" }] },
      { type: "text", value: " " },
      { type: "link", url: "#cite-4", children: [{ type: "text", value: "근거 4" }] },
      { type: "link", url: "#cite-5", children: [{ type: "text", value: "근거 5" }] },
      { type: "text", value: "." },
    ]);
  });

  it("문단 근거 [근거 22¶3]은 그 문단 링크다. 한 표기에 섞어 쓸 수 있다 (2026-10-02 사용자 요청)", () => {
    expect(splitCitations("결과 [근거 22¶3], [근거 20¶1, 22 ¶ 3, 5].")).toEqual([
      { type: "text", value: "결과 " },
      { type: "link", url: "#cite-22p3", children: [{ type: "text", value: "근거 22¶3" }] },
      { type: "text", value: ", " },
      { type: "link", url: "#cite-20p1", children: [{ type: "text", value: "근거 20¶1" }] },
      { type: "link", url: "#cite-22p3", children: [{ type: "text", value: "근거 22¶3" }] },
      { type: "link", url: "#cite-5", children: [{ type: "text", value: "근거 5" }] },
      { type: "text", value: "." },
    ]);
  });

  it("문단 범위 [근거 4¶4–5]는 첫 문단 링크이고 글자는 범위다. 범위가 섞인 표기도 모두 링크다 (2026-10-02 사용자 확인)", () => {
    expect(splitCitations("방법 [근거 4¶4–5]. 증명 [근거 12¶8, 근거 13¶1-12, 근거 19¶35] [근거 24 ¶ 66 ~ 68]")).toEqual([
      { type: "text", value: "방법 " },
      { type: "link", url: "#cite-4p4", children: [{ type: "text", value: "근거 4¶4–5" }] },
      { type: "text", value: ". 증명 " },
      { type: "link", url: "#cite-12p8", children: [{ type: "text", value: "근거 12¶8" }] },
      { type: "link", url: "#cite-13p1", children: [{ type: "text", value: "근거 13¶1–12" }] },
      { type: "link", url: "#cite-19p35", children: [{ type: "text", value: "근거 19¶35" }] },
      { type: "text", value: " " },
      { type: "link", url: "#cite-24p66", children: [{ type: "text", value: "근거 24¶66–68" }] },
    ]);
  });

  it("근거 찾기: 그 문단의 근거가 없으면 같은 번호의 근거로 대신한다", () => {
    const citations = [
      { number: 22, paragraph: 3, block_id: "p3" },
      { number: 22, paragraph: null, block_id: "first" },
      { number: 5, paragraph: null, block_id: "five" },
    ];
    expect(findCitation(citations, 22, 3)?.block_id).toBe("p3");
    expect(findCitation(citations, 22, null)?.block_id).toBe("first");
    expect(findCitation(citations, 5, 2)?.block_id).toBe("five");
    expect(findCitation(citations, 9, null)).toBeUndefined();
  });

  it("논문의 참고문헌 번호 [12]와 [근거 밖]은 근거가 아니다 (2026-10-02 사용자 요청)", () => {
    expect(splitCitations("참고문헌 [12], [3, 4]를 따른다. [근거 밖]")).toBeNull();
  });

  it("이 표기 전에 저장한 답(legacy)은 대괄호 번호를 옛 근거 링크로 바꾼다", () => {
    expect(splitCitations("앞 [1] 뒤 [2, 3].", { legacy: true })).toEqual([
      { type: "text", value: "앞 " },
      { type: "link", url: "#cite-old-1", children: [{ type: "text", value: "[1]" }] },
      { type: "text", value: " 뒤 " },
      { type: "link", url: "#cite-old-2", children: [{ type: "text", value: "[2]" }] },
      { type: "link", url: "#cite-old-3", children: [{ type: "text", value: "[3]" }] },
      { type: "text", value: "." },
    ]);
  });

  it("번호가 없거나 링크 문법이면 바꾸지 않는다", () => {
    expect(splitCitations("근거 없음 [a] [근거 1000]")).toBeNull();
    expect(splitCitations("[1](https://example.com)", { legacy: true })).toBeNull();
  });

  it("근거 표기가 하나라도 있으면 새 표기의 답이다", () => {
    expect(isLegacyAnswer("막대 셋 [1]")).toBe(true);
    expect(isLegacyAnswer("막대 셋 [근거 1], 참고문헌 [12]")).toBe(false);
    expect(isLegacyAnswer("> [근거 밖] 일반 지식 [3]")).toBe(true);
  });

  it("쪽 표기 p.19 · pp. 20–21 · 23쪽은 그 첫 쪽으로 가는 링크가 되고 글자는 그대로다", () => {
    expect(splitCitations("근거 [근거 1] p.19, pp. 20–21 그리고 23쪽.")).toEqual([
      { type: "text", value: "근거 " },
      { type: "link", url: "#cite-1", children: [{ type: "text", value: "근거 1" }] },
      { type: "text", value: " " },
      { type: "link", url: "#page-19", children: [{ type: "text", value: "p.19" }] },
      { type: "text", value: ", " },
      { type: "link", url: "#page-20", children: [{ type: "text", value: "pp. 20–21" }] },
      { type: "text", value: " 그리고 " },
      { type: "link", url: "#page-23", children: [{ type: "text", value: "23쪽" }] },
      { type: "text", value: "." },
    ]);
  });

  it("낱말 속 p.와 0쪽은 쪽 링크로 보지 않는다", () => {
    expect(splitCitations("step.3 app.19 0쪽 3.9쪽")).toBeNull();
  });
});

describe("remarkCitations", () => {
  it("코드와 링크 안의 글은 그대로 둔다", () => {
    const tree = {
      type: "root",
      children: [
        {
          type: "paragraph",
          children: [
            { type: "text", value: "보세요 [근거 1]" },
            { type: "inlineCode", value: "a[근거 1]" },
            { type: "link", url: "https://example.com", children: [{ type: "text", value: "[근거 2]" }] },
          ],
        },
      ],
    };
    remarkCitations()(tree);
    const paragraph = tree.children[0].children;
    expect(paragraph.map((node) => node.type)).toEqual(["text", "link", "inlineCode", "link"]);
    expect(paragraph[1]).toMatchObject({ url: "#cite-1" });
    expect(paragraph[3]).toMatchObject({ url: "https://example.com" });
  });
});

describe("remarkInlineMathTags", () => {
  it("문장 안 수식의 식 번호 \\tag{n}은 KaTeX가 그리지 못하므로 뒤에 붙인 (n)으로 바꾼다 (2026-10-02 사용자 확인: 빨간 글자)", () => {
    // remark-math는 HTML로 넘길 글(data.hChildren)을 파싱할 때 따로 담는다. 둘 다 바꿔야 그려진다.
    const inlineMath = (value: string) => ({ type: "inlineMath", value, data: { hChildren: [{ type: "text", value }] } });
    const tree = {
      type: "root",
      children: [
        {
          type: "paragraph",
          children: [inlineMath("S = \\sum_{u} A_{i,u} \\tag{1.4}"), inlineMath("x \\tag*{(*)}"), inlineMath("y = 1")],
        },
        { type: "math", value: "z \\tag{2}" }, // 따로 쓴 수식은 \tag를 그린다
      ],
    };
    remarkInlineMathTags()(tree);
    const [inline, starred, plain] = tree.children[0].children!.map((node) => [node.value, node.data!.hChildren[0].value]);
    expect(inline).toEqual(Array(2).fill("S = \\sum_{u} A_{i,u} \\qquad\\text{(1.4)}"));
    expect(starred).toEqual(Array(2).fill("x \\qquad\\text{(*)}"));
    expect(plain).toEqual(["y = 1", "y = 1"]);
    expect(tree.children[1].value).toBe("z \\tag{2}");
  });
});

describe("remarkOutsideEvidence", () => {
  const quote = (text: string) => ({
    type: "blockquote",
    children: [{ type: "paragraph", children: [{ type: "text", value: text }] }],
  });

  it("[근거 밖]으로 시작하는 인용문에 표시를 달고 그 표기는 지운다", () => {
    const tree = { type: "root", children: [quote("[근거 밖] 전역 스케줄링은 코어를 옮겨 다닌다."), quote("원문 인용")] };
    remarkOutsideEvidence()(tree);
    const [outside, plain] = tree.children as { data?: unknown; children: { children: { value: string }[] }[] }[];
    expect(outside.data).toEqual({ hProperties: { className: ["outside-evidence"] } });
    expect(outside.children[0].children[0].value).toBe("전역 스케줄링은 코어를 옮겨 다닌다.");
    expect(plain.data).toBeUndefined();
    expect(plain.children[0].children[0].value).toBe("원문 인용");
  });
});
