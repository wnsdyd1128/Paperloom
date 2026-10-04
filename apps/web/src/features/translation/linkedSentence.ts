/**
 * 원문 문장 → 번역 문장 강조 (2026-10-04 사용자 요청: 번역 → 원문 강조의 반대 방향). 원문 쪽에서 마우스 아래의 번역한
 * 문단(줄 상자)과 문장 묶음을 찾는다. 문장 묶음의 원문 줄 quad는 번역 → 원문 강조와 같다(sourceHighlight.sentenceQuads).
 * 저장된 번역만 읽는다(번역을 실행하지 않는다). 끄는 동안(글·영역 고르기)은 하지 않는다.
 */
import { type RefObject, useEffect, useRef } from "react";

import type { Quad } from "../reader/geometry";
import { clientRectToPageBox, type PageTarget } from "../reader/selection";
import { sentenceGroups } from "./sentences";
import { sentenceQuads } from "./sourceHighlight";
import type { SourceHover } from "./TranslatedPage";
import type { PageEntry } from "./useTranslation";

/** 강조할 번역 문장: 쪽·문단·문장 묶음 차례(sentenceGroups). null이면 없다 */
export type LinkedSentence = Readonly<{ pageIndex: number; blockId: string; group: number }> | null;

const SLACK = 0.006; // 정규화 좌표. 줄 사이·낱말 사이 틈도 그 줄로 본다(먼저 틈 없이 찾는다)

function inside([u0, v0, u1, v1]: readonly number[], u: number, v: number, slack: number): boolean {
  return u >= u0 - slack && u <= u1 + slack && v >= v0 - slack && v <= v1 + slack;
}

function quadBox(quad: Quad): number[] {
  const us = [quad[0], quad[2], quad[4], quad[6]];
  const vs = [quad[1], quad[3], quad[5], quad[7]];
  return [Math.min(...us), Math.min(...vs), Math.max(...us), Math.max(...vs)];
}

/** 점(정규화 좌표)이 든 줄 상자(regions: [u0, v0, u1, v1])의 문단 */
export function blockAtPoint<T extends Readonly<{ regions: readonly (readonly number[])[] }>>(blocks: readonly T[], u: number, v: number): T | null {
  for (const slack of [0, SLACK]) {
    const found = blocks.find((block) => block.regions.some((region) => inside(region, u, v, slack)));
    if (found) return found;
  }
  return null;
}

/** 점이 든 quad의 문장 묶음 차례 */
export function groupAtPoint(groups: readonly (readonly Quad[])[], u: number, v: number): number | null {
  for (const slack of [0, SLACK]) {
    const index = groups.findIndex((quads) => quads.some((quad) => inside(quadBox(quad), u, v, slack)));
    if (index >= 0) return index;
  }
  return null;
}

type Options = Readonly<{
  enabled: boolean;
  resolvePage: (pageIndex: number) => PageTarget | null;
  entry: (pageIndex: number) => PageEntry | undefined;
  /** 그 쪽의 저장된 번역을 읽는다(없으면 번역 없음으로 둔다) */
  load: (pageIndex: number) => void;
  /** 마우스 아래 문장이 바뀌면 부른다(없어지면 null). hover는 그 원문 문장(원문 쪽 강조용) */
  onChange: (linked: LinkedSentence, hover: SourceHover) => void;
}>;

export function useLinkedSentence(containerRef: RefObject<HTMLElement | null>, options: Options) {
  const latest = useRef(options);
  useEffect(() => {
    latest.current = options;
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !options.enabled) return;
    const quadsCache = new Map<string, readonly (readonly Quad[])[]>();
    let current: string | null = null;
    let frame = 0;

    const emit = (linked: LinkedSentence, hover: SourceHover) => {
      const key = linked && `${linked.pageIndex}:${linked.blockId}:${linked.group}`;
      if (key === current) return;
      current = key;
      latest.current.onChange(linked, hover);
    };

    const find = (x: number, y: number): [LinkedSentence, SourceHover] => {
      const pageElement = document.elementFromPoint(x, y)?.closest<HTMLElement>(".page");
      const pageIndex = pageElement ? Number(pageElement.dataset.pageNumber) - 1 : -1;
      const target = pageIndex >= 0 ? latest.current.resolvePage(pageIndex) : null;
      if (!target) return [null, null];
      const entry = latest.current.entry(pageIndex);
      if (entry === undefined) latest.current.load(pageIndex);
      if (entry?.status !== "ready") return [null, null];
      const { u0: u, v0: v } = clientRectToPageBox(target, { left: x, top: y, right: x, bottom: y });
      const sources = new Map(entry.blocks.map((block) => [block.block_id, block]));
      const candidates = entry.translation.blocks.flatMap((item) => {
        const block = sources.get(item.block_id);
        return block ? [{ item, block, regions: block.regions }] : [];
      });
      const hit = blockAtPoint(candidates, u, v);
      if (!hit) return [null, null];
      const groups = sentenceGroups(hit.item.sentences);
      const key = `${pageIndex}:${hit.block.block_id}:${entry.translation.created_at}`;
      let quads = quadsCache.get(key);
      if (!quads) {
        if (!target.element.querySelector(".textLayer")?.textContent) return [null, null]; // 글 층을 아직 그리지 않았다(다음에 다시)
        quads = groups.map((group) => sentenceQuads(target, hit.block, group.ranges) ?? []); // 찾지 못한 문장은 고르지 않는다
        quadsCache.set(key, quads);
      }
      const group = groupAtPoint(quads, u, v);
      if (group === null) return [null, null];
      const block = { block_id: hit.block.block_id, text: hit.block.text, regions: hit.block.regions };
      return [{ pageIndex, blockId: block.block_id, group }, { pageIndex, block, ranges: groups[group].ranges }];
    };

    const onMove = (event: PointerEvent) => {
      cancelAnimationFrame(frame);
      if (event.buttons !== 0) return emit(null, null);
      const { clientX, clientY } = event;
      frame = requestAnimationFrame(() => emit(...find(clientX, clientY)));
    };
    const onLeave = () => {
      cancelAnimationFrame(frame);
      emit(null, null);
    };
    container.addEventListener("pointermove", onMove);
    container.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      container.removeEventListener("pointermove", onMove);
      container.removeEventListener("pointerleave", onLeave);
      emit(null, null);
    };
  }, [containerRef, options.enabled]);
}
