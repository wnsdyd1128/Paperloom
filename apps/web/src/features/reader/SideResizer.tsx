import { type KeyboardEvent, type PointerEvent, useState } from "react";

/**
 * 사이드바 너비 조절 (2026-10-02 사용자 요청: 대화창 왼쪽 경계에 마우스를 대면 크기를 바꾼다). 왼쪽 경계를 끌거나,
 * 경계에 포커스를 두고 ←·→로 바꾼다. 너비는 이 브라우저에만 기억한다(편의 설정).
 */
export const SIDE_WIDTH = { initial: 420, min: 320, max: 960, minStage: 360, step: 24 } as const;
const STORAGE_KEY = "paperloom.reader.sideWidth";

/** 최소·최대 사이로, 그리고 창에 본문 자리(minStage)가 남게. 정수 px */
export function clampSideWidth(width: number, viewport: number): number {
  const upper = Math.max(SIDE_WIDTH.min, Math.min(SIDE_WIDTH.max, viewport - SIDE_WIDTH.minStage));
  return Math.round(Math.min(Math.max(width, SIDE_WIDTH.min), upper));
}

function storedWidth(): number {
  try {
    const value = Number(localStorage.getItem(STORAGE_KEY));
    return value > 0 ? clampSideWidth(value, window.innerWidth) : SIDE_WIDTH.initial;
  } catch {
    return SIDE_WIDTH.initial;
  }
}

function remember(width: number): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(width));
  } catch {
    // 기억하지 못해도 이번 화면에서는 바뀐다
  }
}

/** 사이드바 너비와 그 왼쪽 경계 손잡이 */
export function useSideWidth() {
  const [width, setWidth] = useState(storedWidth);
  const apply = (next: number, save: boolean) => {
    const clamped = clampSideWidth(next, window.innerWidth);
    setWidth(clamped);
    if (save) remember(clamped);
  };

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault(); // 끄는 동안 글을 고르지 않는다
    const handle = event.currentTarget;
    const startX = event.clientX;
    const startWidth = width;
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add("is-resizing-side");
    // 왼쪽 경계를 왼쪽으로 끌면 넓어진다
    const move = (next: globalThis.PointerEvent) => apply(startWidth + (startX - next.clientX), false);
    const end = (last: globalThis.PointerEvent) => {
      apply(startWidth + (startX - last.clientX), true);
      document.body.classList.remove("is-resizing-side");
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const delta = event.key === "ArrowLeft" ? SIDE_WIDTH.step : event.key === "ArrowRight" ? -SIDE_WIDTH.step : 0;
    if (!delta) return;
    event.preventDefault();
    apply(width + delta, true);
  }

  const handle = (
    <div
      className="side-resizer"
      role="separator"
      aria-orientation="vertical"
      aria-label="사이드바 너비 (끌거나 ←·→)"
      aria-valuenow={width}
      aria-valuemin={SIDE_WIDTH.min}
      aria-valuemax={SIDE_WIDTH.max}
      tabIndex={0}
      title="끌어서 대화창 너비 바꾸기"
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
    />
  );
  return { width, handle };
}
