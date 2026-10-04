/**
 * 번역문에 마우스를 올린 동안 원문 쪽에 그 원문 문장을 강조한다 (U7, 2026-10-03 사용자 요청). 문장은 text layer에서
 * 글로 찾아(locateText) 선택과 같은 규칙으로 줄 quad로 바꾼다. text layer가 아직 없거나 찾지 못하면 문단 전체를 강조한다.
 */
import { boxToQuad, type Quad } from "../reader/geometry";
import { type PageTarget, rangesToPageQuads } from "../reader/selection";
import { locateText } from "./locate";
import type { SourceHover } from "./TranslatedPage";

export function sourceQuads(target: PageTarget, hover: NonNullable<SourceHover>): Quad[] {
  return sentenceQuads(target, hover.block, hover.ranges) ?? regionsQuads(hover.block.regions);
}

/**
 * 문단 text 안 범위들(한 문장 묶음)의 원문 줄 quad(정본 좌표). text layer가 아직 없거나 글을 찾지 못하면 null.
 * 원문 문장 → 번역 문장 강조(linkedSentence)도 같은 quad로 마우스 아래 문장을 고른다.
 */
export function sentenceQuads(target: PageTarget, block: NonNullable<SourceHover>["block"], ranges: readonly (readonly [number, number])[]): Quad[] | null {
  const layer = target.element.querySelector(".textLayer");
  const nodes: Text[] = [];
  if (layer) {
    const walker = document.createTreeWalker(layer, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text);
  }
  const parts = nodes.map((node) => node.data);
  const found: Range[] = [];
  for (const [start, end] of ranges) {
    const at = locateText(parts, block.text.slice(start, end), block.text);
    if (!at) return null;
    const range = document.createRange();
    range.setStart(nodes[at.start.node], at.start.offset);
    range.setEnd(nodes[at.end.node], at.end.offset);
    found.push(range);
  }
  const quads = rangesToPageQuads(found, [target])[0]?.quads ?? [];
  return quads.length > 0 ? [...quads] : null;
}

function regionsQuads(regions: readonly (readonly number[])[]): Quad[] {
  return regions.map(([u0, v0, u1, v1]) => boxToQuad({ u0, v0, u1, v1 }));
}
