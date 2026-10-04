/**
 * 영역 선택 모드 (W04a, IMPL §10.6): 본문 위에서 끈 사각형을 그 쪽의 정규화 quad 하나로 만든다.
 *
 * 텍스트 선택과 같은 변환(clientRectToPageBox)을 써서 보기 회전·확대·DPR과 무관한 정본 좌표가 된다.
 * 끄는 동안 쪽 안에 점선 사각형을 보이고, 쪽 밖으로 나간 부분은 잘라낸다. Esc는 모드를 끝낸다.
 * 모드가 꺼져 있어도 Ctrl(Mac은 Cmd)을 누른 채 끌면 바로 영역을 고른다(빠른 실행).
 */
import { type RefObject, useEffect, useRef } from "react";

import { boxToQuad, type Quad } from "./geometry";
import { clientRectToPageBox, contentFrame, type PageTarget } from "./selection";

export type RegionSelection = Readonly<{ pageIndex: number; quad: Quad }>;

// 클릭이나 손 떨림 정도의 끌기는 영역으로 보지 않는다.
const MIN_REGION_CSS_PX = 6;

type Callbacks = Readonly<{
  resolvePage: (pageIndex: number) => PageTarget | null;
  onRegion: (region: RegionSelection) => void;
  onExit: () => void;
}>;

export function useRegionDrawing(containerRef: RefObject<HTMLDivElement | null>, active: boolean, callbacks: Callbacks) {
  // 핸들러는 모드가 켜질 때 한 번 등록하므로 최신 콜백을 ref로 읽는다.
  const latest = useRef(callbacks);
  const activeRef = useRef(active);
  useEffect(() => {
    latest.current = callbacks;
    activeRef.current = active;
  });

  useEffect(() => {
    const container = containerRef.current!;
    // 시작점은 쪽 기준 좌표로 둔다. 끄는 도중 스크롤해도 같은 지점을 가리킨다.
    let drag: { target: PageTarget; startX: number; startY: number; band: HTMLDivElement } | null = null;

    const pointIn = (target: PageTarget, clientX: number, clientY: number) => {
      const frame = contentFrame(target.element);
      return {
        frame,
        x: Math.min(Math.max(clientX - frame.left, 0), frame.width),
        y: Math.min(Math.max(clientY - frame.top, 0), frame.height),
      };
    };
    const currentRect = (event: PointerEvent) => {
      const { frame, x, y } = pointIn(drag!.target, event.clientX, event.clientY);
      const local = {
        left: Math.min(drag!.startX, x),
        top: Math.min(drag!.startY, y),
        right: Math.max(drag!.startX, x),
        bottom: Math.max(drag!.startY, y),
      };
      const client = {
        left: frame.left + local.left,
        top: frame.top + local.top,
        right: frame.left + local.right,
        bottom: frame.top + local.bottom,
      };
      return { local, client };
    };
    const drawBand = (event: PointerEvent) => {
      const { local } = currentRect(event);
      Object.assign(drag!.band.style, {
        left: `${local.left}px`,
        top: `${local.top}px`,
        width: `${local.right - local.left}px`,
        height: `${local.bottom - local.top}px`,
      });
    };
    const stop = () => {
      drag?.band.remove();
      drag = null;
    };

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0 || !(activeRef.current || event.ctrlKey || event.metaKey)) return;
      const pageElement = (event.target as Element).closest<HTMLElement>(".page");
      const target = pageElement && latest.current.resolvePage(Number(pageElement.dataset.pageNumber) - 1);
      if (!target) return;
      event.preventDefault(); // 텍스트 선택·끌어 놓기를 시작하지 않는다
      container.setPointerCapture(event.pointerId);
      const { x, y } = pointIn(target, event.clientX, event.clientY);
      const band = document.createElement("div");
      band.className = "region-band";
      target.element.append(band);
      drag = { target, startX: x, startY: y, band };
      drawBand(event);
    };
    const onPointerMove = (event: PointerEvent) => {
      if (drag) drawBand(event);
    };
    const onPointerUp = (event: PointerEvent) => {
      if (!drag) return;
      const { local, client } = currentRect(event);
      const target = drag.target;
      stop();
      if (local.right - local.left < MIN_REGION_CSS_PX || local.bottom - local.top < MIN_REGION_CSS_PX) return;
      latest.current.onRegion({ pageIndex: target.pageIndex, quad: boxToQuad(clientRectToPageBox(target, client)) });
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      stop();
      if (activeRef.current) latest.current.onExit();
    };

    container.addEventListener("pointerdown", onPointerDown);
    container.addEventListener("pointermove", onPointerMove);
    container.addEventListener("pointerup", onPointerUp);
    container.addEventListener("pointercancel", stop);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      stop();
      container.removeEventListener("pointerdown", onPointerDown);
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerup", onPointerUp);
      container.removeEventListener("pointercancel", stop);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [containerRef]);
}
