import { describe, expect, it } from "vitest";

import type { Annotation } from "../annotations/api";
import type { InlineThread } from "../threads/useInlineThreads";
import { annotatedPdfUrl, pdfFileName, pdfPartCounts } from "./pdfExport";

const annotation = (color: Annotation["color"], comment: string): Annotation => ({ color, comment }) as unknown as Annotation;

const thread = (kind: InlineThread["kind"], versionId: string, saved = true): InlineThread =>
  ({ kind, anchor: { version_id: versionId }, thread: saved ? { session_id: "s" } : null }) as unknown as InlineThread;

describe("annotatedPdfUrl", () => {
  it("고른 것을 include로 하나씩 보낸다", () => {
    expect(annotatedPdfUrl("v 1", ["highlights", "questions"])).toBe("/api/v1/versions/v%201/annotated-pdf?include=highlights&include=questions");
  });
});

describe("pdfPartCounts", () => {
  it("하이라이트는 색이 있는 주석, 주석은 메모가 있는 주석, 설명·AI 질문은 이 판본의 저장된 대화를 센다", () => {
    const annotations = [annotation("c1", ""), annotation("c2", "하이라이트의 메모"), annotation(null, "메모"), annotation(null, "  ")];
    const threads = [thread("explain", "v1"), thread("ask", "v1"), thread("ask", "v1"), thread("translate", "v1"), thread("ask", "v0"), thread("explain", "v1", false)];

    expect(pdfPartCounts(annotations, threads, "v1")).toEqual({ highlights: 2, notes: 2, explanations: 1, questions: 2 });
  });
});

describe("pdfFileName", () => {
  it("제목에서 파일 이름에 못 쓰는 글자를 _로 바꾼다", () => {
    expect(pdfFileName("CROS-RT: Cross-Layer Scheduling?")).toBe("CROS-RT_ Cross-Layer Scheduling_.pdf");
    expect(pdfFileName(`a${String.fromCharCode(92)}b/c${String.fromCharCode(9)}d`)).toBe("a_b_c_d.pdf");
    expect(pdfFileName("  ")).toBe("논문.pdf");
  });
});
