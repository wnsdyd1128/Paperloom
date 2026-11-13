/**
 * 주석을 넣은 PDF 내보내기 (2026-11-13 사용자 요청). 서버가 원본 PDF 뒤에 고른 것을 PDF 표준 주석으로 붙인다
 * (backend/src/paperloom/pdf_export). 사이드바의 Claude 대화와 번역은 넣지 않는다.
 */
import type { IconName } from "../../shared/Icon";
import type { Annotation } from "../annotations/api";
import type { InlineThread } from "../threads/useInlineThreads";

/** 넣을 수 있는 것 (서버의 pdf_export.marks.Part) */
export type PdfPart = "highlights" | "notes" | "explanations" | "questions";

/** 선택 메뉴와 같은 이름·그림 */
export const PDF_PARTS: readonly Readonly<{ part: PdfPart; label: string; icon: IconName }>[] = [
  { part: "highlights", label: "하이라이트", icon: "highlighter" },
  { part: "notes", label: "주석", icon: "note" },
  { part: "explanations", label: "설명", icon: "sparkles" },
  { part: "questions", label: "AI 질문", icon: "ask" },
];

export function annotatedPdfUrl(versionId: string, parts: readonly PdfPart[]): string {
  const query = new URLSearchParams(parts.map((part) => ["include", part]));
  return `/api/v1/versions/${encodeURIComponent(versionId)}/annotated-pdf?${query}`;
}

/**
 * 부분마다 PDF에 들어갈 수. 하이라이트는 색이 있는 주석, 주석은 메모가 있는 주석(하이라이트에 단 메모도 센다),
 * 설명·AI 질문은 이 판본에서 시작해 저장된 원문 위 대화다(답을 아직 받는 중인 새 대화는 빠진다).
 */
export function pdfPartCounts(annotations: readonly Annotation[], threads: readonly InlineThread[], versionId: string): Record<PdfPart, number> {
  const saved = (kind: InlineThread["kind"]) => threads.filter((item) => item.thread && item.kind === kind && item.anchor.version_id === versionId).length;
  return {
    highlights: annotations.filter((item) => item.color !== null).length,
    notes: annotations.filter((item) => item.comment.trim()).length,
    explanations: saved("explain"),
    questions: saved("ask"),
  };
}

const NOT_IN_FILE_NAMES = new Set(["/", String.fromCharCode(92), ":", "*", "?", '"', "<", ">", "|"]);

/** 내려받을 파일 이름: 논문 제목에서 Windows 파일 이름에 쓸 수 없는 글자(제어 문자 포함)를 _로 바꾼다 */
export function pdfFileName(title: string): string {
  const base = Array.from(title, (char) => (char.charCodeAt(0) < 32 || NOT_IN_FILE_NAMES.has(char) ? "_" : char))
    .join("")
    .trim();
  return `${base || "논문"}.pdf`;
}
