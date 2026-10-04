/**
 * 참고문헌 번호 따라가기 (2026-10-02 사용자 요청): 본문의 "[25]" 같은 번호를 Ctrl(Mac은 Cmd)을 누른 채 끌지 않고
 * 누르면, 하이퍼링크처럼 참고문헌 쪽의 그 항목으로 스크롤해 강조한다. Ctrl을 누른 채 끌면 영역 선택이다(regionDrawing).
 *
 * PDF의 링크 주석은 쓰지 않는다(Reader는 annotation layer를 끄고, 링크가 없는 PDF도 많다). 누른 글자 둘레의 text layer
 * 글에서 대괄호 번호를 읽고, 본문 추출이 참고문헌으로 표시한 쪽("references", backend documents.references)의 문단에서
 * 그 번호로 시작하는 항목을 찾는다. 저자·연도 꼴 인용("Hardy et al., 2017")은 따라가지 않는다.
 * Ctrl을 누르고 번호 위에 있으면 링크처럼 손가락 커서다. 돌아가기는 viewReturn이다.
 */
import { type RefObject, useEffect, useRef } from "react";

import { getPageBlocks, type TextBlock } from "../library/api";
import { CLICK_SLOP_PX } from "./figures";
import { boxToQuad } from "./geometry";
import type { FocusedText } from "./textFocus";

const GROUP = /\[([^[\]]{1,80})\]/g;
// "3", "3, 7", "12–15", "1,2;5-7"
const NUMERIC = /^\s*\d+(?:\s*[,;\-–—]\s*\d+)*\s*$/;
// 참고문헌 항목의 시작: 문단 첫머리나 빈칸 뒤의 "[25]"
const ENTRY = /(?:^|\s)\[(\d+)\]/g;
// 누른 글 노드 앞뒤로 함께 읽을 글 노드 수. 번호가 "[", "25", "]"처럼 여러 조각으로 나뉘거나, 찾기 강조(U4)가
// 조각 안의 글을 강조 span으로 나눌 수 있다.
const NEIGHBOR_NODES = 4;

/** text의 offset 글자가 숫자 인용("[3]", "[3, 7]", "[12–15]") 안이면 누른 번호. 괄호·쉼표를 누르면 첫 번호, 인용이 아니면 null */
export function citedNumberAt(text: string, offset: number): number | null {
  for (const group of text.matchAll(GROUP)) {
    const start = group.index!;
    if (offset < start || offset >= start + group[0].length) continue;
    if (!NUMERIC.test(group[1])) return null;
    const inner = offset - start - 1;
    const numbers = [...group[1].matchAll(/\d+/g)];
    const pressed = numbers.find((number) => inner >= number.index! && inner < number.index! + number[0].length);
    return Number((pressed ?? numbers[0])[0]);
  }
  return null;
}

/** 참고문헌 항목 문단의 번호들: "[n]"으로 시작하면 그 안의 항목 시작마다, "n."으로 시작하면 그 번호, 아니면 없음 */
function entryNumbers(text: string): number[] {
  const trimmed = text.trim();
  if (/^\[\d+\]/.test(trimmed)) return [...trimmed.matchAll(ENTRY)].map((match) => Number(match[1]));
  const dotted = /^(\d+)\.\s/.exec(trimmed);
  return dotted ? [Number(dotted[1])] : [];
}

export type ReferenceEntry = Readonly<{ blockId: string; regions: TextBlock["regions"] }>;

/**
 * 참고문헌 쪽 문단(읽는 순서)에서 number번 항목. 그 번호로 시작하는 문단을 먼저 찾고, 없으면 한 줄짜리 항목이 이어 붙은
 * 문단("[1] … [2] …": 본문 추출은 같은 곳에서 시작하는 줄을 한 문단으로 묶는다)에서 찾는다. 이어 붙은 문단은 항목 수가
 * 줄 수와 같으면 그 줄만, 아니면 문단 전체를 준다.
 */
export function referenceEntry(blocks: readonly TextBlock[], number: number): ReferenceEntry | null {
  const listed = blocks.map((block) => ({ block, numbers: entryNumbers(block.text) }));
  const found = listed.find(({ numbers }) => numbers[0] === number) ?? listed.find(({ numbers }) => numbers.includes(number));
  if (!found) return null;
  const { block, numbers } = found;
  const oneLine = numbers.length > 1 && numbers.length === block.regions.length;
  return { blockId: block.block_id, regions: oneLine ? [block.regions[numbers.indexOf(number)]] : block.regions };
}

/**
 * 점 아래 text layer 글 노드와 그 앞뒤 몇 노드를 이은 글, 그 안에서 점에 가장 가까운 글자의 자리. 글자가 없으면 null.
 * span이 아니라 글 노드로 본다: 찾기 강조(PDF.js TextHighlighter)는 조각의 글을 강조 span과 나머지 글로 나눈다.
 */
function textAt(x: number, y: number): { text: string; offset: number } | null {
  const element = document.elementsFromPoint(x, y).find((item) => item.matches(".textLayer span"));
  const layer = element?.closest(".textLayer");
  if (!element || !layer) return null;
  const nodes = textNodes(layer);
  let hit: { node: Text; index: number; gap: number } | null = null;
  for (const node of nodes) {
    if (!element.contains(node)) continue;
    const nearest = nearestChar(node, x, y);
    if (!hit || nearest.gap < hit.gap) hit = { node, ...nearest };
  }
  if (!hit) return null;
  const at = nodes.indexOf(hit.node);
  const join = (items: Text[]) => items.map((node) => node.data).join("");
  const before = join(nodes.slice(Math.max(0, at - NEIGHBOR_NODES), at));
  const after = join(nodes.slice(at + 1, at + 1 + NEIGHBOR_NODES));
  return { text: before + hit.node.data + after, offset: before.length + hit.index };
}

function textNodes(root: Element): Text[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  return nodes;
}

/** 점 아래 글자가 숫자 인용 안이면 그 번호 */
function citationAt(x: number, y: number): number | null {
  const hit = textAt(x, y);
  return hit && citedNumberAt(hit.text, hit.offset);
}

/** 점에 가장 가까운 글자와 그 거리. text layer 조각은 늘이거나 돌려 그리므로 글자마다 화면 상자를 잰다. */
function nearestChar(node: Text, x: number, y: number): { index: number; gap: number } {
  const range = document.createRange();
  let nearest = 0;
  let distance = Infinity;
  for (let index = 0; index < node.length; index++) {
    range.setStart(node, index);
    range.setEnd(node, index + 1);
    const rect = range.getBoundingClientRect();
    const gap = Math.hypot(Math.max(rect.left - x, 0, x - rect.right), Math.max(rect.top - y, 0, y - rect.bottom));
    if (gap < distance) [nearest, distance] = [index, gap];
  }
  return { index: nearest, gap: distance };
}

type Options = Readonly<{
  versionId: string;
  /** 본문 추출이 참고문헌으로 표시한 쪽(0부터, 차례대로). 추출이 끝나기 전에는 비어 있다. */
  referencePages: readonly number[];
  /** 찾은 항목으로 간다. 항목을 찾지 못했으면 quads가 빈 참고문헌 첫 쪽이다. */
  onFollow: (target: FocusedText) => void;
  /** 참고문헌 쪽이나 항목을 찾지 못한 까닭 */
  onMiss: (message: string) => void;
}>;

/** 쪽 문단은 처음 따라갈 때 받아 두고, 버전이 바뀌면 버린다. 마지막 누름만 따라간다. */
export function useReferenceLinks(containerRef: RefObject<HTMLDivElement | null>, options: Options) {
  const latest = useRef(options);
  useEffect(() => {
    latest.current = options;
  });

  useEffect(() => {
    const container = containerRef.current!;
    const blocks = new Map<number, Promise<readonly TextBlock[]>>();
    let pressed: { x: number; y: number } | null = null;
    let presses = 0;
    let cancelled = false;

    const pageBlocks = (pageIndex: number) => {
      let list = blocks.get(pageIndex);
      if (!list) {
        list = getPageBlocks(options.versionId, pageIndex).catch(() => {
          blocks.delete(pageIndex); // 못 받았으면 다음 누름에 다시 받는다
          return [];
        });
        blocks.set(pageIndex, list);
      }
      return list;
    };
    const follow = async (number: number) => {
      const press = ++presses;
      const { referencePages } = latest.current;
      if (referencePages.length === 0) {
        latest.current.onMiss(`참고문헌 쪽을 찾지 못해 [${number}]로 갈 수 없습니다.`);
        return;
      }
      const lists = await Promise.all(referencePages.map(pageBlocks));
      if (cancelled || press !== presses) return;
      for (const [index, list] of lists.entries()) {
        const entry = referenceEntry(list, number);
        if (!entry) continue;
        const quads = entry.regions.map(([u0, v0, u1, v1]) => boxToQuad({ u0, v0, u1, v1 }));
        latest.current.onFollow({ pageIndex: referencePages[index], quads });
        return;
      }
      latest.current.onFollow({ pageIndex: referencePages[0], quads: [] });
      latest.current.onMiss(`참고문헌에서 [${number}] 항목을 찾지 못해 참고문헌 첫 쪽을 열었습니다.`);
    };

    const onPointerDown = (event: PointerEvent) => {
      const onPage = (event.target as Element).closest(".pdfViewer .page") !== null;
      pressed = event.button === 0 && (event.ctrlKey || event.metaKey) && onPage ? { x: event.clientX, y: event.clientY } : null;
    };
    // click 이벤트는 쓰지 않는다: Ctrl 누름은 영역 끌기가 포인터를 스크롤 영역에 붙잡아(pointer capture) target이 쪽이 아니다.
    const onPointerUp = (event: PointerEvent) => {
      const start = pressed;
      pressed = null;
      if (!start || Math.hypot(event.clientX - start.x, event.clientY - start.y) > CLICK_SLOP_PX) return;
      const number = citationAt(event.clientX, event.clientY);
      if (number !== null) void follow(number);
    };

    // 손가락 커서: 포인터가 쪽 위에 있을 때 Ctrl을 누른 채 움직이거나, 움직이지 않고 Ctrl만 눌러도 다시 본다.
    let pointer: { x: number; y: number } | null = null;
    let frame = 0;
    const showCursor = (ctrl: boolean) => {
      cancelAnimationFrame(frame);
      const at = pointer;
      if (!ctrl || !at) {
        container.classList.remove("over-citation");
        return;
      }
      frame = requestAnimationFrame(() => container.classList.toggle("over-citation", citationAt(at.x, at.y) !== null));
    };
    const onPointerMove = (event: PointerEvent) => {
      // 영역을 끄는 동안은 포인터를 스크롤 영역이 붙잡아 target이 쪽이 아니다: 손가락을 보이지 않는다.
      pointer = (event.target as Element).closest(".pdfViewer .page") ? { x: event.clientX, y: event.clientY } : null;
      showCursor(event.ctrlKey || event.metaKey);
    };
    const onPointerLeave = () => {
      pointer = null;
      showCursor(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Control" || event.key === "Meta") showCursor(event.ctrlKey || event.metaKey);
    };

    container.addEventListener("pointerdown", onPointerDown);
    container.addEventListener("pointerup", onPointerUp);
    container.addEventListener("pointermove", onPointerMove);
    container.addEventListener("pointerleave", onPointerLeave);
    document.addEventListener("keydown", onKey);
    document.addEventListener("keyup", onKey);
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      container.classList.remove("over-citation");
      container.removeEventListener("pointerdown", onPointerDown);
      container.removeEventListener("pointerup", onPointerUp);
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerleave", onPointerLeave);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("keyup", onKey);
    };
  }, [containerRef, options.versionId]);
}
