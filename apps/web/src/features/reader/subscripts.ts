/**
 * 선택 속 첨자·분수 추정 (IMPL §5.4).
 *
 * PDF에는 첨자·분수 구조가 없고 글자 조각과 위치만 있다. 같은 줄에서 기준 글자보다 작고 세로로 벗어난
 * 조각을 아래첨자(`_`)·위첨자(`^`)로, 앞 글자와 떨어져 위아래로 겹쳐 놓인 작은 글자 두 묶음을 문장 속
 * 분수(`\frac{분자}{분모}`)로 추정한다. 결과는 추정이며 원문 인용(quote)을 대신하지 않는다.
 * 본문 크기로 조판한 별행 분수, 행렬, 근호, 위아래 극한은 다루지 않는다.
 */
import type { Box } from "./geometry";

/**
 * 한 텍스트 노드에서 선택된 부분과 그 글자(앞뒤 공백 제외)의 상자. 상자는 회전 전 쪽 좌표로
 * 가로·세로가 같은 단위(pt)이고 v는 아래로 커진다. DOM 순서로 준다.
 */
export type TextFragment = Readonly<{ text: string; box: Box }>;

// 줄의 기준 글자 높이(H)에 대한 비율. TeX 첨자는 보통 0.7H 크기, 가운데가 0.3H 안팎 벗어난다.
const MAX_SCRIPT_SIZE = 0.9;
const MIN_SCRIPT_SHIFT = 0.15;
const MIN_REFERENCE_SHARE = 0.25;
// 분수와 겹친 첨자(f^j_k)는 크기·세로 위치가 같고, 앞 글자와의 간격만 다르다. 아래첨자는 앞 글자에
// 붙고(실제 논문 측정 0.06H 이하), TeX는 분수 앞에 적어도 \nulldelimiterspace(약 0.13 em)를 둔다.
const MIN_FRACTION_GAP = 0.1;
// 분자와 분모 묶음의 가로 범위가 좁은 쪽 폭의 절반 이상 겹쳐야 위아래로 놓인 것으로 본다.
const MIN_FRACTION_OVERLAP = 0.5;

// small: 기준보다 작지만 제자리에 있는 글자(스몰캡, 분자 속 첨자가 기준선 가까이 온 경우). 첨자 구간을
// 시작하지는 않지만 이미 시작한 구간 안에서는 앞 조각의 묶음에 붙는다.
type Kind = "normal" | "small" | "sub" | "sup";

/** 첨자나 분수를 찾으면 추정 표기를, 찾지 못하면 null을 돌려준다. */
export function estimateScriptedQuote(fragments: readonly TextFragment[]): string | null {
  const lines = groupLines(fragments).map((line) => renderLine(line, true));
  if (!lines.some((line) => line.found)) return null;
  return lines
    .map((line) => line.text)
    .join(" ")
    .replace(/\s+/g, " ")
    .replace(/ ([_^])/g, "$1") // 첨자 앞 공백: "C _k" → "C_k"
    .replace(/([_^](?:\{[^}]*\}|[^\s{])|\})\s+(?=[,.;:)\]])/g, "$1") // 첨자·분수 뒤 문장부호 앞 공백
    .trim();
}

/** 한 줄(또는 분자·분모 묶음)을 표기한다. 분수는 줄 수준에서만 찾는다. */
function renderLine(line: readonly TextFragment[], findFractions: boolean): { text: string; found: boolean } {
  const { kinds, height } = classify(line);
  const parts: string[] = [];
  let found = false;
  let lastRight: number | null = null; // 앞에 있는 본문 글자의 오른쪽 끝
  for (let index = 0; index < line.length; ) {
    if (kinds[index] === "normal" || kinds[index] === "small") {
      parts.push(line[index].text);
      if (isPrintable(line[index])) lastRight = line[index].box.u1;
      index++;
      continue;
    }
    // 첨자 조각이 이어지는 구간. 사이에 낀 공백·small 조각은 구간에 넣는다.
    let end = index;
    for (let next = index; next < line.length && !(kinds[next] === "normal" && isPrintable(line[next])); next++) {
      if (kinds[next] === "sub" || kinds[next] === "sup") end = next;
    }
    const run = line.slice(index, end + 1);
    const runKinds = kinds.slice(index, end + 1);
    const fraction = findFractions ? asFraction(run, runKinds, lastRight, height) : null;
    if (fraction) {
      parts.push(`\\frac{${renderGroup(fraction.upper)}}{${renderGroup(fraction.lower)}}`);
    } else {
      parts.push(renderScripts(run, runKinds));
    }
    found = true;
    lastRight = Math.max(...run.map((fragment) => fragment.box.u1));
    index = end + 1;
  }
  return { text: parts.join(""), found };
}

/**
 * 첨자 구간이 문장 속 분수인지 본다. 위로 벗어난 묶음과 아래로 벗어난 묶음이 한 번씩(순서는 무관) 나오고,
 * 둘이 가로로 겹치며, 앞 본문 글자와 떨어져 있으면 분수다. 겹친 첨자(f^j_k)는 앞 글자에 붙어 있어 빠진다.
 */
function asFraction(
  run: readonly TextFragment[],
  kinds: readonly Kind[],
  lastRight: number | null,
  height: number,
): { upper: TextFragment[]; lower: TextFragment[] } | null {
  const pieces = run.map((fragment, index) => ({ fragment, kind: kinds[index] })).filter(({ fragment }) => isPrintable(fragment));
  pieces.forEach((piece, index) => {
    if (piece.kind === "small") piece.kind = pieces[index - 1].kind; // 구간은 첨자로 시작하므로 앞 조각이 있다
  });
  const split = pieces.findIndex(({ kind }) => kind !== pieces[0].kind);
  if (split < 0 || pieces.slice(split).some(({ kind }) => kind === pieces[0].kind)) return null;
  const first = pieces.slice(0, split).map(({ fragment }) => fragment);
  const second = pieces.slice(split).map(({ fragment }) => fragment);
  const [upper, lower] = pieces[0].kind === "sup" ? [first, second] : [second, first];
  const a = extent(upper);
  const b = extent(lower);
  const overlap = Math.min(a.u1, b.u1) - Math.max(a.u0, b.u0);
  if (overlap < MIN_FRACTION_OVERLAP * Math.min(a.u1 - a.u0, b.u1 - b.u0)) return null;
  if (lastRight !== null && Math.min(a.u0, b.u0) - lastRight < MIN_FRACTION_GAP * height) return null;
  return { upper, lower };
}

/**
 * 분수가 아닌 첨자 구간. 같은 쪽으로 이어진 조각은 한 첨자로 묶는다: PDF.js가 "i", ",", "k"로 나눈
 * 아래첨자는 `_{i,k}`다. 방향이 바뀌면(위→아래) 새 첨자다: `f^j_k`.
 */
function renderScripts(run: readonly TextFragment[], kinds: readonly Kind[]): string {
  const parts: string[] = [];
  let group: { kind: "sub" | "sup"; text: string } | null = null;
  const flush = () => {
    if (group) parts.push(script(group.kind, group.text));
    group = null;
  };
  run.forEach((fragment, index) => {
    const kind = kinds[index] === "small" && group ? group.kind : kinds[index];
    if (kind === "sub" || kind === "sup") {
      if (group?.kind !== kind) {
        flush();
        group = { kind, text: "" };
      }
      group.text += fragment.text;
    } else if (group && !isPrintable(fragment)) {
      group.text += fragment.text; // 첨자 안 공백. 앞뒤 공백은 script()가 지운다
    } else {
      flush();
      parts.push(fragment.text);
    }
  });
  flush();
  return parts.join("");
}

/** 분자·분모 묶음: 그 묶음의 글자 크기를 기준으로 다시 첨자를 찾는다 (C_i). */
function renderGroup(fragments: readonly TextFragment[]): string {
  return renderLine(fragments, false).text.trim();
}

function script(kind: Kind, text: string): string {
  if (kind === "normal" || kind === "small") return text;
  const body = text.trim();
  return (kind === "sub" ? "_" : "^") + (body.length === 1 ? body : `{${body}}`);
}

/** DOM 순서를 지키며 세로로 겹치는(짧은 쪽 높이의 절반 이상) 조각을 한 줄로 묶는다. */
function groupLines(fragments: readonly TextFragment[]): TextFragment[][] {
  const lines: { v0: number; v1: number; items: TextFragment[] }[] = [];
  for (const fragment of fragments) {
    const { v0, v1 } = fragment.box;
    const last = lines.at(-1);
    const overlap = last ? Math.min(last.v1, v1) - Math.max(last.v0, v0) : 0;
    if (last && overlap >= 0.5 * Math.min(last.v1 - last.v0, v1 - v0)) {
      last.items.push(fragment);
      last.v0 = Math.min(last.v0, v0);
      last.v1 = Math.max(last.v1, v1);
    } else {
      lines.push({ v0, v1, items: [fragment] });
    }
  }
  return lines.map((line) => line.items);
}

function classify(line: readonly TextFragment[]): { kinds: Kind[]; height: number } {
  const printable = line.filter(isPrintable);
  const height = referenceHeight(printable);
  const base = printable.filter((fragment) => fragmentHeight(fragment) > MAX_SCRIPT_SIZE * height);
  const center = weightedMedian(base.map((fragment) => [fragmentCenter(fragment), weight(fragment)]));
  const kinds = line.map((fragment): Kind => {
    if (!isPrintable(fragment) || fragmentHeight(fragment) > MAX_SCRIPT_SIZE * height) return "normal";
    const shift = (fragmentCenter(fragment) - center) / height;
    if (shift > MIN_SCRIPT_SHIFT) return "sub";
    if (shift < -MIN_SCRIPT_SHIFT) return "sup";
    return "small";
  });
  return { kinds, height };
}

/**
 * 줄의 기준 글자 높이: 비슷한 높이(±10%)의 글자가 줄 글자의 25% 이상인 높이 중 가장 큰 값.
 * 수식만 고르면 첨자 글자 수가 본문 글자보다 많을 수 있어 중앙값은 쓰지 않는다. 큰 연산자(∑) 하나는
 * 25%에 못 미쳐 기준이 되지 않는다.
 */
function referenceHeight(printable: readonly TextFragment[]): number {
  const total = printable.reduce((sum, fragment) => sum + weight(fragment), 0);
  const heights = printable.map(fragmentHeight).sort((a, b) => b - a);
  for (const candidate of heights) {
    const similar = printable.filter((fragment) => Math.abs(fragmentHeight(fragment) - candidate) <= 0.1 * candidate);
    if (similar.reduce((sum, fragment) => sum + weight(fragment), 0) >= MIN_REFERENCE_SHARE * total) return candidate;
  }
  return heights[0] ?? 0;
}

function extent(fragments: readonly TextFragment[]): { u0: number; u1: number } {
  return {
    u0: Math.min(...fragments.map((fragment) => fragment.box.u0)),
    u1: Math.max(...fragments.map((fragment) => fragment.box.u1)),
  };
}

function isPrintable(fragment: TextFragment): boolean {
  return fragment.text.trim().length > 0;
}

function fragmentHeight({ box }: TextFragment): number {
  return box.v1 - box.v0;
}

function fragmentCenter({ box }: TextFragment): number {
  return (box.v0 + box.v1) / 2;
}

function weight(fragment: TextFragment): number {
  return fragment.text.replace(/\s/g, "").length;
}

function weightedMedian(entries: readonly (readonly [number, number])[]): number {
  const sorted = [...entries].sort(([a], [b]) => a - b);
  const half = sorted.reduce((sum, [, w]) => sum + w, 0) / 2;
  let seen = 0;
  for (const [value, w] of sorted) {
    seen += w;
    if (seen >= half) return value;
  }
  return sorted.at(-1)?.[0] ?? 0;
}
