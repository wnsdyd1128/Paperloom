import { describe, expect, it } from "vitest";

import { pageInfos, scrollDelta, viewPosition } from "./channel";
import { blockAtPoint, groupAtPoint } from "./linkedSentence";
import { locateText } from "./locate";
import { batchProgress, nextPageToTranslate, type PageInfo } from "./schedule";
import { sentenceGroups } from "./sentences";
import { blockFrame, singleLineRoom, styledRuns, wholeMark } from "./typeset";

const page = (pageIndex: number, extra: Partial<PageInfo> = {}): PageInfo => ({ pageIndex, hasText: true, ...extra });
// 2: 글 없는 쪽, 4: 참고문헌·그림·표뿐인 쪽(본문 없음)
const pages = [page(0), page(1), page(2, { hasText: false }), page(3), page(4, { hasText: false }), page(5)];
const none = new Set<number>();

describe("nextPageToTranslate (D3·D10: 보는 쪽만, 바로. 일괄 번역은 사용자가 시작)", () => {
  it("지금 쪽을 먼저, 한 번에 한 쪽", () => {
    expect(nextPageToTranslate({ current: 3, pages, done: none, skip: none, batch: false })).toBe(3);
    expect(nextPageToTranslate({ current: 3, pages, done: new Set([3]), skip: none, batch: false })).toBeNull();
  });

  it("글·본문 없는 쪽·실패한 쪽은 저절로 번역하지 않는다", () => {
    for (const current of [2, 4]) expect(nextPageToTranslate({ current, pages, done: none, skip: none, batch: false })).toBeNull();
    expect(nextPageToTranslate({ current: 1, pages, done: none, skip: new Set([1]), batch: false })).toBeNull();
  });

  it("일괄 번역 중이면 지금 쪽 다음에 앞쪽부터 남은 쪽(글·본문 없는 쪽 제외)", () => {
    expect(nextPageToTranslate({ current: 5, pages, done: none, skip: none, batch: true })).toBe(5);
    expect(nextPageToTranslate({ current: 5, pages, done: new Set([5, 0]), skip: none, batch: true })).toBe(1);
    expect(nextPageToTranslate({ current: 4, pages, done: new Set([0, 1, 3]), skip: new Set([5]), batch: true })).toBeNull();
  });

  it("일괄 번역 진행: 글·본문 없는 쪽을 뺀 쪽 가운데 번역한 쪽", () => {
    expect(batchProgress(pages, new Set([0, 4]))).toEqual({ done: 1, total: 4 });
  });
});

describe("pageInfos (쪽 추출 상태 → 번역 차례, 2026-10-03 사용자 요청: 참고문헌 쪽 전체가 아니라 참고문헌 부분만 뺀다)", () => {
  it("참고문헌 쪽이어도 본문(결론 등)이 있으면 번역하고, 글이 없거나 본문이 없는 쪽은 건너뛴다", () => {
    expect(
      pageInfos([
        { page_index: 0, text_status: "usable", flags: ["references"] },
        { page_index: 1, text_status: "usable", flags: ["references", "no_body_text"] },
        { page_index: 2, text_status: "image_only", flags: [] },
        { page_index: 3, text_status: "partial", flags: ["no_text"] },
        { page_index: 4, text_status: "partial", flags: ["two_columns"] },
      ]),
    ).toEqual([
      { pageIndex: 0, hasText: true },
      { pageIndex: 1, hasText: false },
      { pageIndex: 2, hasText: false },
      { pageIndex: 3, hasText: false },
      { pageIndex: 4, hasText: true },
    ]);
  });
});

describe("locateText (번역 문장의 원문을 text layer에서 찾기)", () => {
  const parts = ["The left col", "umn opens with a sched-", "ulability test. ", "It uses the ﬁxed ", "point. The left column again."];

  it("글 조각을 넘나들고, 공백·줄 끝 하이픈·합자·대소문자를 무시한다", () => {
    const found = locateText(parts, "It uses the fixed point.")!;
    expect(found).toEqual({ start: { node: 3, offset: 0 }, end: { node: 4, offset: 6 } });
    expect(locateText(parts, "column opens with a schedulability test.")).toEqual({ start: { node: 0, offset: 9 }, end: { node: 2, offset: 15 } });
  });

  it("같은 글이 여럿이면 문단(near) 안에서 먼저 찾고, 없으면 null", () => {
    expect(locateText(parts, "The left column", "point. The left column again.")!.start).toEqual({ node: 4, offset: 7 });
    expect(locateText(parts, "The left column")!.start).toEqual({ node: 0, offset: 0 });
    expect(locateText(parts, "not on this page")).toBeNull();
    expect(locateText(parts, "  ")).toBeNull();
  });

  it("수학 글자(𝐿 U+1D43F처럼 UTF-16 두 칸)가 든 문장도 찾고, 끝은 그 글자 뒤다 (TCPS 2쪽, 2026-10-05)", () => {
    const math = ["sepa-", "rate for", " ", "𝐿", "1", " ", "caches yet unified at the", " ", "𝐿𝐿𝐶", " ", "level."];
    expect(locateText(math, "separate for 𝐿1 caches yet unified at the 𝐿𝐿𝐶 level.")).toEqual({ start: { node: 0, offset: 0 }, end: { node: 10, offset: 6 } });
    expect(locateText(math, "the 𝐿𝐿𝐶")).toEqual({ start: { node: 6, offset: 22 }, end: { node: 8, offset: 6 } });
    expect(locateText(["at level L1."], "at level 𝐿1.")).toEqual({ start: { node: 0, offset: 0 }, end: { node: 0, offset: 12 } }); // 서버만 수학 글자여도 같은 글자로 본다
  });
});

describe("sentenceGroups (빈 번역은 앞 문장과 합쳐 옮긴 것)", () => {
  it("빈 번역의 원문 범위를 앞 묶음에 더한다", () => {
    const sentences = [
      { start: 0, end: 10, text: "가" },
      { start: 11, end: 20, text: "" },
      { start: 21, end: 30, text: "나" },
    ];
    expect(sentenceGroups(sentences)).toEqual([
      { text: "가", ranges: [[0, 10], [11, 20]] },
      { text: "나", ranges: [[21, 30]] },
    ]);
  });

  it("문단 첫 문장이 비면(PDF에서 나뉜 문장을 앞 문단 끝에 합쳐 옮김) 빈 묶음으로 두고 다음 문장부터 그린다", () => {
    expect(sentenceGroups([{ start: 0, end: 10, text: "" }, { start: 11, end: 20, text: "다" }])).toEqual([
      { text: "", ranges: [[0, 10]] },
      { text: "다", ranges: [[11, 20]] },
    ]);
  });
});

describe("styledRuns (번역문의 <b>·<i> 표시, 2026-10-03 사용자 요청: 원문 굵게·기울임 유지)", () => {
  it("표시를 모양 구간으로 바꾸고 겹친 표시·대문자 표시도 읽는다", () => {
    expect(styledRuns("<b>실시간 스케줄링.</b> 두 코어에서 <i>deg2rad</i>를 <B><i>모두</i></B> 쓴다.")).toEqual([
      { text: "실시간 스케줄링.", bold: true, italic: false },
      { text: " 두 코어에서 ", bold: false, italic: false },
      { text: "deg2rad", bold: false, italic: true },
      { text: "를 ", bold: false, italic: false },
      { text: "모두", bold: true, italic: true },
      { text: " 쓴다.", bold: false, italic: false },
    ]);
  });

  it("다른 태그 모양은 글 그대로, 닫지 않은 표시는 끝까지, 짝 없는 닫기는 무시", () => {
    expect(styledRuns("a <script>x</script> <u>y</u>")).toEqual([{ text: "a <script>x</script> <u>y</u>", bold: false, italic: false }]);
    expect(styledRuns("앞 <b>뒤")).toEqual([
      { text: "앞 ", bold: false, italic: false },
      { text: "뒤", bold: true, italic: false },
    ]);
    expect(styledRuns("</i>그냥 <b></b>글")).toEqual([{ text: "그냥 글", bold: false, italic: false }]);
  });
});

describe("styledRuns 위·아래첨자 (2026-10-04 사용자 확인: 인라인 수식이 납작해졌다)", () => {
  it("<sub>·<sup>을 아래·위첨자로 읽고 기울임과 겹쳐도 된다", () => {
    expect(styledRuns("C<sub>k</sub> 와 <i>τ<sup>na</sup><sub>p</sub></i>")).toEqual([
      { text: "C", bold: false, italic: false },
      { text: "k", bold: false, italic: false, script: "sub" },
      { text: " 와 ", bold: false, italic: false },
      { text: "τ", bold: false, italic: true },
      { text: "na", bold: false, italic: true, script: "sup" },
      { text: "p", bold: false, italic: true, script: "sub" },
    ]);
  });
});

describe("wholeMark (문단 전체 모양: 번역이 표시를 빼도 제목은 굵게)", () => {
  it("한 구간이 문단 전체면 그 모양, 아니면 없음", () => {
    expect(wholeMark({ text: "5.2 Scheduling", styles: [[0, 14, "b"]] })).toBe("b");
    expect(wholeMark({ text: "5.2 Scheduling", styles: [[4, 14, "b"]] })).toBe("");
    expect(wholeMark({ text: "Plain", styles: [] })).toBe("");
    expect(wholeMark({ text: "Odd", styles: [[0, 3, "x"]] })).toBe("");
  });
});

describe("blockAtPoint·groupAtPoint (원문 문장 → 번역 문장 강조, 2026-10-04 사용자 요청)", () => {
  // 정규화 좌표(위가 0). 문단 둘: 줄 둘, 줄 하나
  const blocks = [
    { block_id: "b1", regions: [[0.1, 0.1, 0.9, 0.12], [0.1, 0.125, 0.5, 0.145]] },
    { block_id: "b2", regions: [[0.1, 0.2, 0.9, 0.22]] },
  ];
  const quad = (u0: number, v0: number, u1: number, v1: number) => [u0, v0, u1, v0, u1, v1, u0, v1] as const;

  it("점이 든 줄 상자의 문단. 줄 사이 좁은 틈은 그 문단으로 보고, 문단 밖은 없다", () => {
    expect(blockAtPoint(blocks, 0.3, 0.11)?.block_id).toBe("b1");
    expect(blockAtPoint(blocks, 0.3, 0.1225)?.block_id).toBe("b1"); // 줄 사이
    expect(blockAtPoint(blocks, 0.3, 0.21)?.block_id).toBe("b2");
    expect(blockAtPoint(blocks, 0.7, 0.135)).toBeNull(); // 둘째 줄은 0.5에서 끝난다
    expect(blockAtPoint(blocks, 0.3, 0.17)).toBeNull();
  });

  it("점이 든 quad의 문장 묶음. 걸친 줄의 앞뒤 문장을 줄 안 위치로 가른다", () => {
    // 묶음 0은 첫 줄 앞쪽, 묶음 1은 첫 줄 뒤쪽과 둘째 줄
    const groups = [[quad(0.1, 0.1, 0.4, 0.12)], [quad(0.41, 0.1, 0.9, 0.12), quad(0.1, 0.125, 0.5, 0.145)]];
    expect(groupAtPoint(groups, 0.2, 0.11)).toBe(0);
    expect(groupAtPoint(groups, 0.6, 0.11)).toBe(1);
    expect(groupAtPoint(groups, 0.2, 0.14)).toBe(1);
    expect(groupAtPoint(groups, 0.405, 0.11)).not.toBeNull(); // 낱말 사이 틈
    expect(groupAtPoint(groups, 0.95, 0.11)).toBeNull();
  });
});

describe("viewPosition·scrollDelta (별도 탭과 쪽 안 자리까지 맞춘다, 2026-10-04 사용자 확인)", () => {
  const frames = [
    { top: 10, height: 100 },
    { top: 120, height: 100 },
    { top: 230, height: 100 },
  ];

  it("보이는 영역 위끝이 걸친 쪽과 그 쪽 높이에 대한 자리", () => {
    expect(viewPosition(160, frames)).toEqual({ pageIndex: 1, offset: 0.4 });
    expect(viewPosition(5, frames)).toEqual({ pageIndex: 0, offset: -0.05 }); // 첫 쪽 위 여백
    expect(viewPosition(115, frames)).toEqual({ pageIndex: 0, offset: 1.05 }); // 쪽 사이 틈은 앞 쪽의 1 너머
  });

  it("다른 창(쪽 크기가 다르다)에서 같은 쪽의 같은 자리를 위끝에 두는 스크롤 양", () => {
    expect(scrollDelta(50, { top: 300, height: 200 }, 0.4)).toBe(330); // 300 + 0.4 × 200 - 50
    expect(scrollDelta(50, { top: 20, height: 200 }, 0)).toBe(-30);
  });
});

describe("blockFrame (레이아웃 유지 문단: 원문 글꼴 크기·줄 간격, 2026-10-03 사용자 요청)", () => {
  const line = (top: number, left = 100, right = 400, height = 12) => ({ left, top, right, bottom: top + height });

  it("여러 줄: 글꼴은 원문 pt × 쪽 배율 × 고른 배율, 줄 간격은 원문 줄 사이(글꼴 비율), 상자는 줄 수 × 줄 사이", () => {
    const frame = blockFrame([line(200), line(216), line(232)], 10, 4 / 3, 1);
    expect(frame.single).toBe(false);
    expect(frame.fontSize).toBeCloseTo(13.333, 3);
    expect(frame.lineHeight).toBe("1.2"); // 16px / 13.33px
    expect(frame).toMatchObject({ left: 100, width: 300, height: 48, top: 198 }); // 반 줄 간격만큼 위로
    expect(blockFrame([line(200), line(216), line(232)], 10, 4 / 3, 0.8).fontSize).toBeCloseTo(10.667, 3);
  });

  it("글꼴 크기가 없는 전 추출 문단은 줄 높이로 어림하고, 줄이 겹쳐 줄 사이를 못 재면 줄 높이 × 1.2", () => {
    expect(blockFrame([line(200), line(216)], null, 1, 1).fontSize).toBeCloseTo(12 * 0.78, 3);
    const rotated = blockFrame([line(200, 100, 110, 300), line(200, 120, 130, 300)], 10, 1, 1);
    expect(rotated.height).toBeCloseTo(24, 3);
  });

  it("위·아래첨자로 줄 상자가 줄 사이보다 높아도(상자끼리 겹쳐도) 줄 사이는 잰 값이다: 못 잰 것은 글꼴 크기와 견준다", () => {
    // 사용자 논문 16쪽(2026-10-04): 줄 사이 12.5, 첨자 때문에 줄 상자 16.5 → 줄 상자 × 1.2로 잡아 문단 상자가 1.5배가 되어 아래 문단과 겹쳤다
    const frame = blockFrame([line(100, 100, 400, 16.5), line(112.5, 100, 400, 16.5), line(125, 100, 400, 16.5)], 10, 1, 1);
    expect(frame).toMatchObject({ single: false, height: 37.5, lineHeight: "1.25", top: 102 });
  });

  it("한 줄: 줄 높이(또는 글꼴 × 1.2)를 px 줄 간격으로 두고 원문 줄 가운데에 맞춘다", () => {
    const frame = blockFrame([line(300, 100, 260, 8)], 10, 2, 1);
    expect(frame).toMatchObject({ single: true, left: 100, width: 160, fontSize: 20, height: 24, lineHeight: "24px", top: 292 });
  });

  it("한 줄이 글꼴보다 훨씬 높으면(큰 첫 글자·큰 기호) 가운데가 아니라 위쪽 줄에 둔다(아래 문단에 가리지 않게)", () => {
    expect(blockFrame([line(300, 100, 260, 30)], 10, 1, 1)).toMatchObject({ single: true, top: 300, height: 30, lineHeight: "14px" });
  });

  it("한 줄 문단을 넓힐 폭: 쪽 왼쪽 반에만 놓인 줄(두 단의 왼쪽 단)은 가운데 앞까지, 아니면 쪽 오른쪽 여백까지", () => {
    expect(singleLineRoom({ left: 50, width: 100 }, 600)).toBeCloseTo(238, 5); // 300 - 12 - 50
    expect(singleLineRoom({ left: 350, width: 100 }, 600)).toBeCloseTo(214, 5); // 564 - 350
    expect(singleLineRoom({ left: 50, width: 500 }, 600)).toBeCloseTo(514, 5); // 쪽 폭 줄
    expect(singleLineRoom({ left: 200, width: 400 }, 600)).toBe(400); // 이미 더 넓다
  });
});
