/**
 * 하이라이트 3색 (U5, UI_PLAN §5 U5·A1): 하이라이트는 색이 있는 주석이다. 같은 주석이 메모가 있으면 주석 패널에도 보인다.
 * 색은 시안의 accent-200·accent-400·neutral-300(밝은 판 값)이고, PDF 쪽은 테마와 상관없이 원래 색이므로 화면 견본도
 * 같은 값(--mark-c1…c3)을 쓴다. H는 마지막에 고른 색으로 칠한다(처음은 c1).
 */
import { type MathDelimiters, wrapMath } from "../../shared/mathCopy";
import type { Annotation, HighlightColor } from "./api";

export const HIGHLIGHT_COLORS: readonly HighlightColor[] = ["c1", "c2", "c3"];
export const HIGHLIGHT_COLOR_LABELS: Readonly<Record<HighlightColor, string>> = { c1: "연한 주황", c2: "주황", c3: "회색" };

const COLOR_KEY = "paperloom.reader.highlightColor";

export function storedHighlightColor(): HighlightColor {
  try {
    const value = localStorage.getItem(COLOR_KEY);
    return HIGHLIGHT_COLORS.find((color) => color === value) ?? "c1";
  } catch {
    return "c1"; // 기억하지 못해도 첫 색으로 칠한다
  }
}

export function rememberHighlightColor(color: HighlightColor): void {
  try {
    localStorage.setItem(COLOR_KEY, color);
  } catch {
    // 기억하지 못해도 이번에는 고른 색으로 칠했다
  }
}

/** 색이 있고 고른 색에 드는 주석 가운데, 인용·추정 표기·메모에 찾는 말이 있는 것(대소문자 무시). */
export function filterHighlights(items: readonly Annotation[], colors: ReadonlySet<HighlightColor>, query: string): Annotation[] {
  const needle = query.trim().toLowerCase();
  return items.filter(
    (item) =>
      item.color !== null &&
      colors.has(item.color) &&
      (!needle || `${item.anchor.quote} ${item.anchor.display_quote ?? ""} ${item.comment}`.toLowerCase().includes(needle)),
  );
}

/** "모두 복사": 쪽·인용·메모의 Markdown 목록. 인용은 추정 표기가 있으면 그것(수식 토막은 설정의 구분 기호로 감싼다) */
export function highlightsMarkdown(items: readonly Annotation[], delimiters: MathDelimiters): string {
  return items.map((item) => `- p.${item.anchor.page_index + 1} “${copiedQuote(item.anchor, delimiters)}”${item.comment ? ` — ${item.comment}` : ""}`).join("\n");
}

/** 복사할 인용: 추정 표기가 있으면 수식 토막을 구분 기호로 감싼 그것, 없으면 원문 인용 */
export function copiedQuote(anchor: Annotation["anchor"], delimiters: MathDelimiters): string {
  return anchor.display_quote ? wrapMath(anchor.display_quote, delimiters) : anchor.quote;
}
