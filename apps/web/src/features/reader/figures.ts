/**
 * 그림 클릭 선택: 일반 PDF 뷰어처럼 본문의 그림을 눌러 그림 영역으로 고른다 (IMPL §10.6).
 *
 * 서버가 쪽의 그림 객체(이미지·Form·벡터 경로)를 묶은 후보 상자(정본 좌표)를 주고, 여기서는 포인터 아래의
 * 후보를 찾아 테두리를 보이고, 누르면(끌기 없이) 그 상자를 영역 선택으로 넘긴다. 영역 모드에서도 같다.
 * 텍스트를 끌어 선택한 경우나 영역을 끈 경우에는 고르지 않는다.
 */
import { type RefObject, useEffect, useRef } from "react";

import { parseJson } from "../../shared/http";
import type { Box } from "./geometry";
import { clientRectToPageBox, drawFigureHover, type PageTarget } from "./selection";

export type PageFigure = Readonly<{ box: Box; source: string }>;

// 누른 곳에서 이만큼 넘게 움직였으면 끌기(텍스트 선택·영역 끌기)로 본다.
export const CLICK_SLOP_PX = 6;

export async function fetchPageFigures(versionId: string, pageIndex: number): Promise<PageFigure[]> {
  const url = `/api/v1/versions/${encodeURIComponent(versionId)}/pages/${pageIndex}/figures`;
  const body = await parseJson<{ figures: { box: number[]; source: string }[] }>(await fetch(url));
  return body.figures.map(({ box: [u0, v0, u1, v1], source }) => ({ box: { u0, v0, u1, v1 }, source }));
}

/** 점(정규화 좌표)을 담은 후보 중 가장 작은 것 (겹치면 안쪽 그림). */
export function figureAt(figures: readonly PageFigure[], u: number, v: number): PageFigure | null {
  const inside = figures.filter(({ box }) => u >= box.u0 && u <= box.u1 && v >= box.v0 && v <= box.v1);
  const area = ({ box }: PageFigure) => (box.u1 - box.u0) * (box.v1 - box.v0);
  return inside.sort((a, b) => area(a) - area(b))[0] ?? null;
}

type Options = Readonly<{
  versionId: string;
  resolvePage: (pageIndex: number) => PageTarget | null;
  onPick: (pageIndex: number, figure: PageFigure) => void;
}>;

/** 쪽별 후보는 처음 필요할 때 한 번 받는다. 받기 전에 누르면 아무것도 하지 않는다. `prefetch`로 미리 받는다. */
export function useFigurePicking(containerRef: RefObject<HTMLDivElement | null>, options: Options) {
  const latest = useRef(options);
  useEffect(() => {
    latest.current = options;
  });
  const figures = useRef(new Map<number, readonly PageFigure[] | "loading">());

  function prefetch(pageIndex: number) {
    if (figures.current.has(pageIndex)) return;
    figures.current.set(pageIndex, "loading");
    fetchPageFigures(latest.current.versionId, pageIndex)
      .then((found) => figures.current.set(pageIndex, found))
      .catch(() => figures.current.set(pageIndex, [])); // 후보를 못 받으면 그림 클릭만 안 된다
  }

  useEffect(() => {
    const container = containerRef.current!;
    figures.current.clear();
    let pressed: { x: number; y: number } | null = null;
    let hovered: PageTarget | null = null;
    let frame = 0;

    const hit = (event: PointerEvent) => {
      // 영역 모드는 포인터를 스크롤 영역에 붙잡아(pointer capture) 이벤트 target이 쪽이 아니다. 좌표로 쪽을 찾는다.
      const pageElement = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>(".page");
      const pageIndex = pageElement ? Number(pageElement.dataset.pageNumber) - 1 : -1;
      const target = pageIndex >= 0 ? latest.current.resolvePage(pageIndex) : null;
      if (!target) return null;
      const list = figures.current.get(pageIndex);
      if (list === undefined) prefetch(pageIndex);
      if (!Array.isArray(list)) return { target, figure: null };
      const point = { left: event.clientX, top: event.clientY, right: event.clientX, bottom: event.clientY };
      const { u0, v0 } = clientRectToPageBox(target, point);
      return { target, figure: figureAt(list, u0, v0) };
    };
    const clearHover = () => {
      if (hovered) drawFigureHover(hovered, null);
      hovered = null;
      container.classList.remove("over-figure");
    };

    const onPointerDown = (event: PointerEvent) => {
      pressed = event.button === 0 ? { x: event.clientX, y: event.clientY } : null;
    };
    // click 이벤트는 쓰지 않는다. PDF.js text layer가 누르는 사이 선택 보조 요소(endOfContent)를 옮겨, 두 번째
    // 누름부터는 브라우저가 click을 보내지 않는다. 누른 곳에서 거의 움직이지 않고 뗀 것을 누름으로 본다.
    const onPointerUp = (event: PointerEvent) => {
      const start = pressed;
      pressed = null;
      if (!start || Math.hypot(event.clientX - start.x, event.clientY - start.y) > CLICK_SLOP_PX) return;
      if (!(document.getSelection()?.isCollapsed ?? true)) return; // 텍스트를 선택한 경우
      const found = hit(event);
      if (found?.figure) latest.current.onPick(found.target.pageIndex, found.figure);
    };
    const onPointerMove = (event: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const found = hit(event);
        clearHover();
        if (!found?.figure) return;
        drawFigureHover(found.target, found.figure.box);
        hovered = found.target;
        container.classList.add("over-figure");
      });
    };

    container.addEventListener("pointerdown", onPointerDown);
    container.addEventListener("pointerup", onPointerUp);
    container.addEventListener("pointermove", onPointerMove);
    container.addEventListener("pointerleave", clearHover);
    return () => {
      cancelAnimationFrame(frame);
      clearHover();
      container.removeEventListener("pointerdown", onPointerDown);
      container.removeEventListener("pointerup", onPointerUp);
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerleave", clearHover);
    };
  }, [containerRef, options.versionId]);

  return { prefetch };
}
