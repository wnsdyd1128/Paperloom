import { describe, expect, it } from "vitest";

import { dropText, formatSize, shortName } from "./dropText";

describe("받침 글", () => {
  it("크기는 서버 한도와 같은 MiB·KiB로 쓴다", () => {
    expect(formatSize(2.4 * 1024 ** 2)).toBe("2.4 MiB");
    expect(formatSize(300 * 1024)).toBe("300 KiB");
    expect(formatSize(10)).toBe("1 KiB");
  });

  it("긴 파일 이름은 앞 10자와 끝 8자만 남긴다(한글도 글자 단위)", () => {
    expect(shortName("cache.pdf")).toBe("cache.pdf");
    expect(shortName("a-very-long-paper-name-2026.pdf")).toBe("a-very-lon…2026.pdf");
    expect(shortName("캐시친화성스케줄링연구의실험결과정리본.pdf")).toBe("캐시친화성스케줄링연…과정리본.pdf");
  });

  it("단계마다 두 줄을 바꾼다", () => {
    expect(dropText({ kind: "idle" }, false, true)).toEqual({ title: "PDF를 끌어다 놓으세요", detail: "누르면 파일을 고릅니다 · 100 MiB · 300쪽까지" });
    expect(dropText({ kind: "idle" }, true, true)).toEqual({ title: "놓으면 서재에 등록합니다", detail: "PDF · 100 MiB · 300쪽까지" });
    expect(dropText({ kind: "idle" }, false, false).detail).toBe("PDF · 100 MiB · 300쪽까지");
    expect(dropText({ kind: "sending", name: "cache.pdf", bytes: 2.4 * 1024 ** 2, index: 1, count: 1 }, false, true)).toEqual({
      title: "“cache.pdf” 확인 중",
      detail: "2.4 MiB",
    });
    expect(dropText({ kind: "sending", name: "b.pdf", bytes: 2048, index: 2, count: 3 }, false, false).detail).toBe("2 / 3편 · 2 KiB");
    expect(dropText({ kind: "done", title: "Cache-Aware Scheduling", count: 1 }, false, true)).toEqual({
      title: "서재에 등록했습니다",
      detail: "Cache-Aware Scheduling",
    });
    expect(dropText({ kind: "done", title: "C", count: 3 }, false, true).title).toBe("3편을 등록했습니다");
    expect(dropText({ kind: "failed", message: "PDF 파일만 올릴 수 있습니다." }, false, true)).toEqual({
      title: "등록하지 못했습니다",
      detail: "PDF 파일만 올릴 수 있습니다.",
    });
  });
});
