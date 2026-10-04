/**
 * 번역문의 모양 (U7, 2026-10-03 사용자 요청): 원문의 굵게·기울임을 따르고(브리지가 <b>·<i> 표시로 보내고 받는다),
 * 레이아웃 유지에서는 원문 글꼴 크기·줄 간격으로 같은 여백을 둔다.
 */
import type { TextBlock } from "../library/api";

export type Mark = "" | "b" | "i" | "bi";
/** script: 아래첨자(sub)·위첨자(sup). 없으면 본 글자 */
export type StyledRun = Readonly<{ text: string; bold: boolean; italic: boolean; script?: "sub" | "sup" }>;

const TAG = /<(\/?)(b|i|sub|sup)>/gi;
const MARKS: readonly string[] = ["b", "i", "bi"];

/**
 * 번역문의 <b>·<i>·<sub>·<sup> 표시(브리지 번역 규칙)를 모양 구간으로 바꾼다. 다른 태그 모양을 포함한 나머지는 모두 글
 * 그대로다(HTML로 읽지 않는다). 닫지 않은 표시는 그 글 끝까지, 짝 없는 닫기는 무시한다.
 */
export function styledRuns(text: string): StyledRun[] {
  const runs: StyledRun[] = [];
  const depth: Record<string, number> = { b: 0, i: 0, sub: 0, sup: 0 };
  let at = 0;
  const push = (part: string) => {
    if (!part) return;
    const script = depth.sub > 0 ? "sub" : depth.sup > 0 ? "sup" : undefined;
    const run: StyledRun = { text: part, bold: depth.b > 0, italic: depth.i > 0, ...(script ? { script } : {}) };
    const last = runs[runs.length - 1];
    if (last && last.bold === run.bold && last.italic === run.italic && last.script === run.script) runs[runs.length - 1] = { ...last, text: last.text + part };
    else runs.push(run);
  };
  for (const match of text.matchAll(TAG)) {
    push(text.slice(at, match.index));
    at = match.index + match[0].length;
    const name = match[2].toLowerCase();
    depth[name] = Math.max(0, depth[name] + (match[1] ? -1 : 1));
  }
  push(text.slice(at));
  return runs;
}

/** 문단 전체가 한 모양이면(제목 등) 그 모양. 번역이 표시를 빼도 문단 모양은 따른다. */
export function wholeMark(block: Pick<TextBlock, "text" | "styles">): Mark {
  const runs = block.styles ?? [];
  if (runs.length !== 1) return "";
  const [start, end, mark] = runs[0];
  return start === 0 && end >= block.text.length && MARKS.includes(mark) ? (mark as Mark) : "";
}

export type Rect = Readonly<{ left: number; top: number; right: number; bottom: number }>;
export type BlockFrame = Readonly<{
  left: number;
  top: number;
  width: number;
  height: number;
  /** 처음 글꼴 크기(px). 상자에 넘치면 그리는 쪽에서 줄인다 */
  fontSize: number;
  /** CSS line-height: 여러 줄은 글꼴 비율(줄여도 원문 비율), 한 줄은 px(원문 줄 가운데) */
  lineHeight: string;
  single: boolean;
}>;

/**
 * 한 줄 문단(제목 등)을 넓힐 수 있는 폭: 번역이 원문보다 길면 상자 폭에 맞춰 줄이는 대신 넓힌다. 쪽 왼쪽 반에만 놓인 줄(두 단의
 * 왼쪽 단)은 가운데 앞까지(오른쪽 단 글을 덮지 않게), 아니면 쪽 오른쪽 여백까지.
 */
export function singleLineRoom(frame: Pick<BlockFrame, "left" | "width">, pageWidth: number): number {
  const limit = frame.left + frame.width <= pageWidth / 2 ? pageWidth * 0.48 : pageWidth * 0.94;
  return Math.max(frame.width, limit - frame.left);
}

/**
 * 레이아웃 유지 번역 문단 상자. lines는 원문 줄 상자(CSS px), fontSizePt는 원문 글꼴 크기(pt, 전 추출이면 null → 줄 높이로
 * 어림), viewportScale은 쪽 배율(pt → CSS px), scale은 사용자가 고른 배율(번역 글꼴 단추).
 * 여러 줄 상자는 원문 줄 수 × 줄 사이 높이이고, 반 줄 간격만큼 위로 올려 글줄이 원문 줄과 겹치게 한다.
 */
export function blockFrame(lines: readonly Rect[], fontSizePt: number | null, viewportScale: number, scale: number): BlockFrame {
  const left = Math.min(...lines.map((line) => line.left));
  const right = Math.max(...lines.map((line) => line.right));
  const top = Math.min(...lines.map((line) => line.top));
  const heights = lines.map((line) => Math.min(line.bottom - line.top, line.right - line.left)).sort((a, b) => a - b);
  const lineBox = heights[Math.floor(heights.length / 2)];
  const base = fontSizePt ? fontSizePt * viewportScale : lineBox * 0.78;
  const fontSize = base * scale;
  if (lines.length === 1) {
    // 줄이 글꼴보다 훨씬 높으면(큰 첫 글자·큰 기호) 글줄은 위쪽에 있다: 가운데에 두면 아래 문단에 가린다
    const height = Math.max(lineBox, fontSize * 1.2);
    const lineHeight = Math.min(height, fontSize * 1.4);
    return { left, top: top + (lineBox - height) / 2, width: right - left, height, fontSize, lineHeight: `${lineHeight}px`, single: true };
  }
  const tops = lines.map((line) => line.top).sort((a, b) => a - b);
  const measured = (tops[tops.length - 1] - tops[0]) / (lines.length - 1);
  // 돌린 쪽 등 줄 사이를 못 재면 어림한다. 글꼴 크기와 견준다: 위·아래첨자·큰 기호가 든 줄은 상자가 줄 사이보다 높다(2026-10-04)
  const reference = fontSizePt ? base : lineBox;
  const pitch = measured > reference * 0.8 ? measured : reference * 1.2;
  const ratio = Math.max(1, Math.round((pitch / base) * 1000) / 1000);
  return {
    left,
    top: top - (pitch - lineBox) / 2,
    width: right - left,
    height: lines.length * pitch,
    fontSize,
    lineHeight: String(ratio),
    single: false,
  };
}
