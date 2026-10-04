import { describe, expect, it } from "vitest";

import type { TextBlock } from "../library/api";
import { citedNumberAt, referenceEntry } from "./referenceLinks";

/** text에서 needle의 at번째 글자 자리 */
const at = (text: string, needle: string, offset = 0) => text.indexOf(needle) + offset;

describe("citedNumberAt", () => {
  const text = "Heptane [25] and [3, 7] or [12–15], see [a] and [Smith 2020].";

  it("대괄호 번호 안을 누르면 그 번호다(괄호를 눌러도)", () => {
    expect(citedNumberAt(text, at(text, "25"))).toBe(25);
    expect(citedNumberAt(text, at(text, "25", 1))).toBe(25);
    expect(citedNumberAt(text, at(text, "[25]"))).toBe(25);
    expect(citedNumberAt(text, at(text, "[25]", 3))).toBe(25);
  });

  it("여러 번호면 누른 번호, 쉼표·괄호를 누르면 첫 번호다", () => {
    expect(citedNumberAt(text, at(text, "7]"))).toBe(7);
    expect(citedNumberAt(text, at(text, "3, 7"))).toBe(3);
    expect(citedNumberAt(text, at(text, ", 7"))).toBe(3);
    expect(citedNumberAt(text, at(text, "15]"))).toBe(15);
    expect(citedNumberAt(text, at(text, "–15"))).toBe(12);
  });

  it("대괄호 밖이나 번호가 아닌 대괄호는 null", () => {
    expect(citedNumberAt(text, at(text, "Heptane"))).toBeNull();
    expect(citedNumberAt(text, at(text, " [25]"))).toBeNull();
    expect(citedNumberAt(text, at(text, "a]"))).toBeNull();
    expect(citedNumberAt(text, at(text, "Smith"))).toBeNull();
    expect(citedNumberAt(text, text.length)).toBeNull();
  });

  it("붙은 두 묶음은 누른 쪽이다", () => {
    expect(citedNumberAt("[1][2]", 4)).toBe(2);
    expect(citedNumberAt("[1][2]", 1)).toBe(1);
  });
});

const line = (v: number) => [0.1, v, 0.9, v + 0.01];
const block = (id: string, text: string, lines: number): TextBlock => ({
  block_id: id,
  reading_order: 0,
  text,
  regions: Array.from({ length: lines }, (_, index) => line(0.1 + index * 0.02)),
  styles: [],
  font_size: null,
});

describe("referenceEntry", () => {
  it("번호로 시작하는 항목 문단은 문단 전체다(여러 줄 항목)", () => {
    const blocks = [block("h", "References", 1), block("b24", "[24] A. Author. Title. 2016.", 2), block("b25", "[25] D. Hardy. Heptane. 2017.", 3)];
    expect(referenceEntry(blocks, 25)).toEqual({ blockId: "b25", regions: blocks[2].regions });
  });

  it("한 줄 항목이 이어 붙은 문단은 그 줄만이다", () => {
    const merged = block("m", "[1] A. Author. Cache delay analysis. 2020. [2] B. Author. Cache partitioning. 2021.", 2);
    expect(referenceEntry([merged], 1)).toEqual({ blockId: "m", regions: [merged.regions[0]] });
    expect(referenceEntry([merged], 2)).toEqual({ blockId: "m", regions: [merged.regions[1]] });
  });

  it("항목 수와 줄 수가 다르면 문단 전체다", () => {
    const merged = block("m", "[1] A. Author. A very long title. 2020. [2] B. Author. Short. 2021.", 3);
    expect(referenceEntry([merged], 2)).toEqual({ blockId: "m", regions: merged.regions });
  });

  it("다른 항목이 인용한 번호보다 그 번호로 시작하는 항목이 먼저다", () => {
    const blocks = [block("b10", "[10] X. Extends [12] for caches. 2019.", 2), block("b12", "[12] Y. Original. 2018.", 2)];
    expect(referenceEntry(blocks, 12)?.blockId).toBe("b12");
  });

  it("'25.' 꼴 목록도 찾는다", () => {
    const blocks = [block("b24", "24. A. Author. Title. 2016.", 2), block("b25", "25. D. Hardy. Heptane. 2017.", 2)];
    expect(referenceEntry(blocks, 25)?.blockId).toBe("b25");
  });

  it("본문 문단의 인용이나 없는 번호는 찾지 않는다", () => {
    const blocks = [block("p", "Prior work [1] measured cache delays and [2] split", 1), block("b3", "[3] C. Author. 2022.", 1)];
    expect(referenceEntry(blocks, 2)).toBeNull();
    expect(referenceEntry(blocks, 4)).toBeNull();
  });
});
