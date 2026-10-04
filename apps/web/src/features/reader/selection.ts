/**
 * DOM 선택 → 쪽별 정규화 quad, 정규화 quad → 화면 표시 (IMPL §6.2 선택 처리 순서).
 * 한 Anchor는 한 페이지에 속하므로 여러 쪽에 걸친 선택은 쪽별로 나눈다.
 */
import type { PageViewport } from "pdfjs-dist";

import { type Box, boxToQuad, type CssRect, cssRectToBox, mergeLines, type Quad, quadToCssRect } from "./geometry";
import type { RegionSelection } from "./regionDrawing";
import type { TextFragment } from "./subscripts";

export type PageTarget = Readonly<{ pageIndex: number; element: HTMLElement; viewport: PageViewport }>;
/** 한 쪽의 선택: 줄별 quad와, 첨자·분수 추정(subscripts.ts)에 쓰는 텍스트 조각(DOM 순서, pt 단위). */
export type PageSelection = Readonly<{ pageIndex: number; quads: readonly Quad[]; fragments: readonly TextFragment[] }>;

/**
 * Reader의 현재 선택. 텍스트 선택은 추출된 그대로의 인용(text)과 첨자 추정 표기(displayQuote, 없으면 null)를,
 * 영역 선택(W04a)은 사용자가 끈 사각형 하나를 가진다.
 */
export type ReaderSelection =
  | Readonly<{
      kind: "text";
      text: string;
      displayQuote: string | null;
      prefix: string;
      suffix: string;
      pages: readonly PageSelection[];
    }>
  | (RegionSelection & Readonly<{ kind: "region" }>);

const MIN_RECT_CSS_PX = 0.5; // 폭·높이가 사실상 0인 조각은 버린다

export function selectionToPageQuads(selection: Selection, pages: readonly PageTarget[]): PageSelection[] {
  return rangesToPageQuads(Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index)), pages);
}

/** 글 범위들의 쪽별 줄 quad (선택과 같은 규칙). 쪽 번역의 원문 문장 강조(U7)도 쓴다. */
export function rangesToPageQuads(ranges: readonly Range[], pages: readonly PageTarget[]): PageSelection[] {
  const frames = pages.map((page) => ({ page, frame: contentFrame(page.element) }));
  const boxesByPage = new Map<number, Box[]>();
  const fragmentsByPage = new Map<number, TextFragment[]>();
  // 화면 사각형이 속한 쪽과 그 쪽 기준 정규화 상자
  const locate = (rect: CssRect) => {
    const hit = frames.find(({ frame }) => contains(frame, (rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2));
    return hit ? { page: hit.page, box: clientRectToPageBox(hit.page, rect, hit.frame) } : null;
  };
  for (const { rects, text, glyphRect } of selectedTextNodes(ranges)) {
    for (const rect of rects) {
      const hit = locate(rect);
      if (hit) append(boxesByPage, hit.page.pageIndex, hit.box);
    }
    const glyph = glyphRect && locate(glyphRect);
    if (glyph) append(fragmentsByPage, glyph.page.pageIndex, { text, box: toPagePoints(glyph.page.viewport, glyph.box) });
  }
  return [...boxesByPage]
    .sort(([a], [b]) => a - b)
    .map(([pageIndex, boxes]) => ({
      pageIndex,
      quads: mergeLines(boxes).map(boxToQuad),
      fragments: fragmentsByPage.get(pageIndex) ?? [],
    }));
}

/**
 * 화면 사각형(client 좌표)을 그 쪽의 정규화 상자로 바꾼다. 쪽 밖으로 나간 부분은 잘라낸다.
 * 텍스트 선택과 영역 선택(W04a)이 같은 변환을 쓴다.
 */
export function clientRectToPageBox(target: PageTarget, rect: CssRect, frame: Frame = contentFrame(target.element)): Box {
  // 화면의 페이지 크기와 viewport 크기가 다르면(CSS 확대 등) 비율을 보정한다.
  const scaleX = target.viewport.width / frame.width;
  const scaleY = target.viewport.height / frame.height;
  return cssRectToBox(target.viewport, {
    left: (rect.left - frame.left) * scaleX,
    top: (rect.top - frame.top) * scaleY,
    right: (rect.right - frame.left) * scaleX,
    bottom: (rect.bottom - frame.top) * scaleY,
  });
}

function append<T>(map: Map<number, T[]>, key: number, value: T): void {
  map.set(key, [...(map.get(key) ?? []), value]);
}

/** 정규화 상자를 회전 전 쪽의 pt 단위로 바꾼다. 첨자·분수 추정은 가로 간격을 세로 크기와 비교한다. */
function toPagePoints(viewport: PageViewport, box: Box): Box {
  const [x0, y0, x1, y1] = viewport.viewBox;
  const width = x1 - x0;
  const height = y1 - y0;
  return { u0: box.u0 * width, v0: box.v0 * height, u1: box.u1 * width, v1: box.v1 * height };
}

/**
 * 선택 바로 앞·뒤의 text layer 텍스트 (anchor.v1의 prefix·suffix). 공백은 하나로 줄인다.
 * 선택이 이 text layer 안에서 시작하고 끝나지 않으면 빈 문자열이다.
 */
export function surroundingText(range: Range, textLayer: Element, length: number): { prefix: string; suffix: string } {
  if (!textLayer.contains(range.startContainer) || !textLayer.contains(range.endContainer)) return { prefix: "", suffix: "" };
  const before = document.createRange();
  before.selectNodeContents(textLayer);
  before.setEnd(range.startContainer, range.startOffset);
  const after = document.createRange();
  after.selectNodeContents(textLayer);
  after.setStart(range.endContainer, range.endOffset);
  const tidy = (text: string) => text.replace(/\s+/g, " ");
  return { prefix: tidy(before.toString()).slice(-length).trimStart(), suffix: tidy(after.toString()).slice(0, length).trimEnd() };
}

/**
 * 선택에 포함된 텍스트 노드마다: 선택된 부분의 화면 사각형(rects), 그 텍스트, 앞뒤 공백을 뺀 글자 사각형(glyphRect).
 * 각 사각형은 그 텍스트를 담은 요소(text layer span)의 상자와 교차시킨다.
 *
 * 텍스트 조각의 사각형은 글꼴 ascent+descent를 정수 픽셀로 반올림한 높이를 가져서, 같은 텍스트라도
 * 확대에 따라 위·아래가 1px까지 달라진다. span 상자는 글꼴 크기와 같은 높이로 확대에 선형이므로,
 * 교차하면 글 진행 방향은 선택한 범위를, 그 수직 방향은 span을 따르는 확대 무관한 사각형이 된다.
 *
 * 첨자·분수 추정은 글자 사이 간격을 재므로 앞뒤 공백을 뺀 글자 사각형을 쓴다. 공백까지 한 조각으로
 * 그린 PDF에서는 공백을 포함하면 분수 앞 간격이 0이 된다.
 */
function* selectedTextNodes(ranges: readonly Range[]): Generator<{ rects: CssRect[]; text: string; glyphRect: CssRect | null }> {
  for (const range of ranges) {
    for (const node of textNodesIn(range)) {
      const host = node.parentElement?.getBoundingClientRect();
      if (!host) continue;
      const start = node === range.startContainer ? range.startOffset : 0;
      const end = node === range.endContainer ? range.endOffset : node.length;
      const text = node.data.slice(start, end);
      const rects = clippedRects(node, start, end, host);
      const leading = text.length - text.trimStart().length;
      const trailing = text.length - text.trimEnd().length;
      const trimmed = text.trim().length > 0 && leading + trailing > 0;
      const glyphRects = trimmed ? clippedRects(node, start + leading, end - trailing, host) : rects;
      yield { rects, text, glyphRect: union(glyphRects) };
    }
  }
}

function clippedRects(node: Text, start: number, end: number, host: DOMRect): CssRect[] {
  const part = document.createRange();
  part.setStart(node, start);
  part.setEnd(node, end);
  return [...part.getClientRects()]
    .map((rect) => ({
      left: Math.max(rect.left, host.left),
      top: Math.max(rect.top, host.top),
      right: Math.min(rect.right, host.right),
      bottom: Math.min(rect.bottom, host.bottom),
    }))
    .filter((rect) => rect.right - rect.left >= MIN_RECT_CSS_PX && rect.bottom - rect.top >= MIN_RECT_CSS_PX);
}

function union(rects: readonly CssRect[]): CssRect | null {
  if (rects.length === 0) return null;
  return {
    left: Math.min(...rects.map((rect) => rect.left)),
    top: Math.min(...rects.map((rect) => rect.top)),
    right: Math.max(...rects.map((rect) => rect.right)),
    bottom: Math.max(...rects.map((rect) => rect.bottom)),
  };
}

function textNodesIn(range: Range): Text[] {
  const root = range.commonAncestorContainer;
  if (root instanceof Text) return [root];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (range.intersectsNode(node)) nodes.push(node as Text);
  }
  return nodes;
}

/** 정규화 quad를 현재 viewport로 다시 그린다. PDF.js가 페이지를 다시 그리면 호출해야 한다. */
export function drawQuadOverlay(target: PageTarget, quads: readonly Quad[]): void {
  drawMarks(target, "quad-overlay", quads.map((quad) => ({ quad })));
}

/** 저장된 주석 한 줄의 표시. annotationId는 화면 검증과 스타일에 쓴다. */
/** color가 있으면 그 색의 하이라이트로 그린다(U5, data-color). */
export type AnnotationMark = Readonly<{ quad: Quad; annotationId: string; focused: boolean; color?: string | null }>;

/** 저장된 주석을 선택 표시와 다른 층에 그린다. 링크로 연 위치(focused)는 강조한다. */
export function drawAnnotationOverlay(target: PageTarget, marks: readonly AnnotationMark[]): void {
  drawMarks(target, "annotation-overlay", marks);
}

/** 쪽 번역의 번역문에 마우스를 올린 동안 그 원문 문장 (U7). 빈 목록이면 지운다. */
export function drawSourceOverlay(target: PageTarget, quads: readonly Quad[]): void {
  drawMarks(target, "source-overlay", quads.map((quad) => ({ quad })));
}

/** 포인터 아래 그림 후보의 테두리 (그림 클릭 선택). box가 null이면 지운다. */
export function drawFigureHover(target: PageTarget, box: Box | null): void {
  drawMarks(target, "figure-hover", box ? [{ quad: boxToQuad(box) }] : []);
}

function drawMarks(
  target: PageTarget,
  layerClass: string,
  marks: readonly Readonly<{ quad: Quad; annotationId?: string; focused?: boolean; color?: string | null }>[],
): void {
  const { element, viewport } = target;
  let layer = element.querySelector<HTMLElement>(`:scope > .${layerClass}`);
  if (marks.length === 0) {
    layer?.remove();
    return;
  }
  if (!layer) {
    layer = document.createElement("div");
    layer.className = layerClass;
    element.append(layer);
  }
  // 어떤 viewport 기준으로 그렸는지 남긴다 (화면 검증에서 다시 그리기 완료를 판단).
  layer.dataset.scale = String(viewport.scale);
  layer.dataset.rotation = String(viewport.rotation);
  const frame = contentFrame(element);
  const scaleX = frame.width / viewport.width;
  const scaleY = frame.height / viewport.height;
  layer.replaceChildren(
    ...marks.map(({ quad, annotationId, focused, color }, quadIndex) => {
      const rect = quadToCssRect(viewport, quad);
      const mark = document.createElement("div");
      mark.className = focused ? "quad-mark is-focused" : "quad-mark";
      mark.dataset.quadIndex = String(quadIndex);
      mark.dataset.quad = JSON.stringify(quad); // 정본 좌표 (화면 검증이 읽는다)
      if (annotationId) mark.dataset.annotationId = annotationId;
      if (color) mark.dataset.color = color;
      Object.assign(mark.style, {
        left: `${rect.left * scaleX}px`,
        top: `${rect.top * scaleY}px`,
        width: `${(rect.right - rect.left) * scaleX}px`,
        height: `${(rect.bottom - rect.top) * scaleY}px`,
      });
      return mark;
    }),
  );
}

/** quad의 첫 줄이 스크롤 영역의 위쪽 3분의 1, 가로 가운데에 오도록 스크롤한다 (링크로 연 위치). */
export function scrollQuadIntoView(container: HTMLElement, target: PageTarget, quad: Quad): void {
  const frame = contentFrame(target.element);
  const rect = quadToCssRect(target.viewport, quad);
  const scaleX = frame.width / target.viewport.width;
  const scaleY = frame.height / target.viewport.height;
  const view = container.getBoundingClientRect();
  container.scrollLeft += frame.left + ((rect.left + rect.right) / 2) * scaleX - (view.left + container.clientWidth / 2);
  container.scrollTop += frame.top + rect.top * scaleY - (view.top + container.clientHeight / 3);
}

/** quad들을 감싸는 화면(client) 사각형. 선택 위에 메뉴를 띄울 때 쓴다. */
export function quadsClientRect(target: PageTarget, quads: readonly Quad[]): CssRect | null {
  if (quads.length === 0) return null;
  const frame = contentFrame(target.element);
  const scaleX = frame.width / target.viewport.width;
  const scaleY = frame.height / target.viewport.height;
  const rects = quads.map((quad) => quadToCssRect(target.viewport, quad));
  return {
    left: frame.left + Math.min(...rects.map((rect) => rect.left)) * scaleX,
    top: frame.top + Math.min(...rects.map((rect) => rect.top)) * scaleY,
    right: frame.left + Math.max(...rects.map((rect) => rect.right)) * scaleX,
    bottom: frame.top + Math.max(...rects.map((rect) => rect.bottom)) * scaleY,
  };
}

export type Frame = Readonly<{ left: number; top: number; width: number; height: number }>;

/** 페이지 요소의 내용 영역(테두리 제외)을 화면 좌표로 구한다. */
export function contentFrame(element: HTMLElement): Frame {
  const rect = element.getBoundingClientRect();
  return {
    left: rect.left + element.clientLeft,
    top: rect.top + element.clientTop,
    width: element.clientWidth,
    height: element.clientHeight,
  };
}

function contains(frame: Frame, x: number, y: number): boolean {
  return x >= frame.left && x <= frame.left + frame.width && y >= frame.top && y <= frame.top + frame.height;
}
