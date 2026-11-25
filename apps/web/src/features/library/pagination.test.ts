import { describe, expect, it } from "vitest";

import { clampPage, pageAfterResize, pageCount, pageSlice, pageWindow } from "./pagination";

describe("pageCount", () => {
  it("남는 논문이 있으면 한 페이지를 더하고, 논문이 없어도 한 페이지다", () => {
    expect(pageCount(0, 20)).toBe(1);
    expect(pageCount(20, 20)).toBe(1);
    expect(pageCount(21, 20)).toBe(2);
    expect(pageCount(57, 10)).toBe(6);
  });
});

describe("clampPage", () => {
  it("범위를 넘는 페이지는 처음이나 마지막 페이지가 된다", () => {
    expect(clampPage(0, 57, 10)).toBe(1);
    expect(clampPage(3, 57, 10)).toBe(3);
    expect(clampPage(9, 57, 10)).toBe(6); // 논문을 지워 페이지가 줄었을 때
    expect(clampPage(2, 0, 10)).toBe(1);
  });
});

describe("pageSlice", () => {
  const items = Array.from({ length: 12 }, (_, index) => index + 1);

  it("그 페이지의 논문만 준다. 마지막 페이지는 남은 만큼이다", () => {
    expect(pageSlice(items, 1, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(pageSlice(items, 2, 5)).toEqual([6, 7, 8, 9, 10]);
    expect(pageSlice(items, 3, 5)).toEqual([11, 12]);
  });

  it("범위를 넘는 페이지는 마지막 페이지를 준다", () => {
    expect(pageSlice(items, 7, 5)).toEqual([11, 12]);
    expect(pageSlice([], 2, 5)).toEqual([]);
  });
});

describe("pageAfterResize", () => {
  it("보고 있던 페이지의 첫 논문이 든 페이지로 간다", () => {
    expect(pageAfterResize(3, 5, 10)).toBe(2); // 11번째 논문 → 10편씩이면 2페이지
    expect(pageAfterResize(2, 10, 5)).toBe(3); // 11번째 논문 → 5편씩이면 3페이지
    expect(pageAfterResize(1, 20, 5)).toBe(1);
    expect(pageAfterResize(4, 5, 100)).toBe(1);
  });
});

describe("pageWindow", () => {
  it("일곱 페이지까지는 모두 놓는다", () => {
    expect(pageWindow(1, 1)).toEqual([1]);
    expect(pageWindow(3, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it("여덟 페이지부터는 처음·끝과 지금 페이지 둘레만 두고 늘 일곱 칸이다", () => {
    expect(pageWindow(1, 12)).toEqual([1, 2, 3, 4, 5, null, 12]);
    expect(pageWindow(4, 12)).toEqual([1, 2, 3, 4, 5, null, 12]);
    expect(pageWindow(5, 12)).toEqual([1, null, 4, 5, 6, null, 12]);
    expect(pageWindow(8, 12)).toEqual([1, null, 7, 8, 9, null, 12]);
    expect(pageWindow(9, 12)).toEqual([1, null, 8, 9, 10, 11, 12]);
    expect(pageWindow(12, 12)).toEqual([1, null, 8, 9, 10, 11, 12]);
  });
});
