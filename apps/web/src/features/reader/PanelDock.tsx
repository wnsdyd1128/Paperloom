/**
 * 오른쪽 사이드바 패널 고르기 (2026-11-16 사용자 요청: 늘 56px 열을 차지하던 레일을 없앴다).
 * 사이드바가 닫혀 있으면 PDF 위에 뜬 작은 독(FloatingDock)이다. 끌어서 옮길 수 있고, 놓으면 가까운 왼쪽·오른쪽 가장자리에
 * 붙으며 그 자리(쪽과 높이)를 이 브라우저에 기억한다. 사이드바가 열려 있으면 같은 단추가 사이드바 머리의 탭(PanelTabs)이
 * 된다. 둘 다 "사이드바 패널" 내비게이션이고 단추 이름·눌림 상태·개수 배지가 같다.
 * 움직임은 Motion Studies 공용 spring이다: 끄는 동안 따라오기(900/50), 놓은 뒤 내려앉기(280/22), 나타나기(420/32),
 * 집어 든 독이 살짝 커지기(520/16).
 */
import { useEffect, useRef } from "react";

import { Icon, type IconName } from "../../shared/Icon";
import { clamp, reducedMotion, spring, startLoop, step, tune } from "../../shared/spring";

export type PanelItem<P extends string> = Readonly<{ panel: P; label: string; icon: IconName; count: number }>;

type ButtonProps<P extends string> = Readonly<{ item: PanelItem<P>; pressed: boolean; className: string; onPick: (panel: P) => void }>;

function PanelButton<P extends string>({ item, pressed, className, onPick }: ButtonProps<P>) {
  return (
    <button
      type="button"
      className={className}
      aria-label={item.label}
      aria-pressed={pressed}
      title={pressed ? `${item.label} (다시 누르면 닫기)` : item.label}
      onClick={() => onPick(item.panel)}
    >
      <Icon name={item.icon} size={18} />
      {item.count > 0 && (
        <span className="rail-badge" aria-hidden="true">
          {item.count}
        </span>
      )}
    </button>
  );
}

type TabsProps<P extends string> = Readonly<{ items: readonly PanelItem<P>[]; current: P; onPick: (panel: P) => void; onClose: () => void }>;

/** 열린 사이드바 머리의 탭. 지금 탭을 다시 누르거나 ×를 누르면 닫힌다. */
export function PanelTabs<P extends string>({ items, current, onPick, onClose }: TabsProps<P>) {
  return (
    <nav className="side-tabs" aria-label="사이드바 패널">
      {items.map((item) => (
        <PanelButton key={item.panel} item={item} pressed={item.panel === current} className="side-tab" onPick={onPick} />
      ))}
      <button type="button" className="side-tab side-tab-close" aria-label="사이드바 닫기" title="사이드바 닫기" onClick={onClose}>
        <Icon name="x" size={16} />
      </button>
    </nav>
  );
}

type DockProps<P extends string> = Readonly<{ items: readonly PanelItem<P>[]; onPick: (panel: P) => void }>;

/** 닫힌 사이드바의 떠 있는 독. Reader 본문 영역(.reader-stage) 안에 놓는다. */
export function FloatingDock<P extends string>({ items, onPick }: DockProps<P>) {
  const dock = useRef<HTMLElement>(null);
  useEffect(() => startDock(dock.current!), []);
  return (
    <nav ref={dock} className="reader-dock" aria-label="사이드바 패널">
      <span className="dock-grip" title="끌어서 옮기기" aria-hidden="true">
        <Icon name="grip" size={16} />
      </span>
      {items.map((item) => (
        <PanelButton key={item.panel} item={item} pressed={false} className="dock-button" onPick={onPick} />
      ))}
    </nav>
  );
}

type Place = Readonly<{ side: "left" | "right"; /** 0 맨 위 … 1 맨 아래 */ y: number }>;

const PLACE_KEY = "paperloom.reader.dock"; // 이 브라우저에서만 기억하는 편의 설정
const DEFAULT_PLACE: Place = { side: "right", y: 0.5 };
const MARGIN = 12;
/** 이만큼(px) 움직여야 끌기로 본다. 그보다 적으면 단추 누르기다 */
const DRAG_START = 4;

function storedPlace(): Place {
  try {
    const value = JSON.parse(localStorage.getItem(PLACE_KEY) ?? "null") as Partial<Place> | null;
    if ((value?.side === "left" || value?.side === "right") && typeof value.y === "number") return { side: value.side, y: clamp(value.y, 0, 1) };
  } catch {
    // 기억한 자리를 못 읽으면 기본 자리
  }
  return DEFAULT_PLACE;
}

function storePlace(place: Place) {
  try {
    localStorage.setItem(PLACE_KEY, JSON.stringify(place));
  } catch {
    // 저장소를 못 쓰면 이번만 그 자리에 둔다
  }
}

function startDock(dock: HTMLElement): () => void {
  const stage = dock.parentElement ?? dock;
  const scroller = stage.querySelector<HTMLElement>(".reader-scroll");
  const reduce = reducedMotion();
  let place = storedPlace();

  const bounds = () => {
    const scrollbar = scroller ? scroller.offsetWidth - scroller.clientWidth : 0; // 세로 스크롤 막대를 가리지 않는다
    return {
      left: MARGIN,
      right: Math.max(MARGIN, stage.clientWidth - dock.offsetWidth - MARGIN - scrollbar),
      top: MARGIN,
      bottom: Math.max(MARGIN, stage.clientHeight - dock.offsetHeight - MARGIN),
    };
  };
  const home = () => {
    const b = bounds();
    return { x: place.side === "left" ? b.left : b.right, y: b.top + place.y * (b.bottom - b.top) };
  };

  const start = home();
  const X = spring(start.x, 280, 22, reduce);
  const Y = spring(start.y, 280, 22, reduce);
  const O = spring(0, 420, 32, reduce); // 나타나기
  const L = spring(0, 520, 16, reduce); // 집어 들기
  O.t = 1;
  let drag: { pointer: number; px: number; py: number; x: number; y: number; moved: boolean } | null = null;

  function settle() {
    tune(X, 280, 22, reduce);
    tune(Y, 280, 22, reduce);
    const to = home();
    X.t = to.x;
    Y.t = to.y;
  }

  // 끈 뒤 손을 뗀 자리의 click은 단추를 누른 것이 아니다
  const swallow = (event: MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
  };

  function down(event: PointerEvent) {
    if (event.button !== 0) return;
    drag = { pointer: event.pointerId, px: event.clientX, py: event.clientY, x: X.x, y: Y.x, moved: false };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  }

  function move(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.pointer) return;
    const dx = event.clientX - drag.px;
    const dy = event.clientY - drag.py;
    if (!drag.moved) {
      if (Math.hypot(dx, dy) < DRAG_START) return;
      drag.moved = true;
      dock.dataset.dragging = "";
      tune(X, 900, 50, reduce);
      tune(Y, 900, 50, reduce);
      L.t = 1;
    }
    const b = bounds();
    X.t = clamp(drag.x + dx, b.left, b.right);
    Y.t = clamp(drag.y + dy, b.top, b.bottom);
  }

  function up(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.pointer) return;
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
    const moved = drag.moved;
    drag = null;
    if (!moved) return;
    delete dock.dataset.dragging;
    L.t = 0;
    const b = bounds();
    place = {
      side: X.t + dock.offsetWidth / 2 < stage.clientWidth / 2 ? "left" : "right",
      y: b.bottom > b.top ? clamp((Y.t - b.top) / (b.bottom - b.top), 0, 1) : 0,
    };
    storePlace(place);
    settle();
    window.addEventListener("click", swallow, { capture: true, once: true });
    setTimeout(() => window.removeEventListener("click", swallow, { capture: true }), 0);
  }

  dock.addEventListener("pointerdown", down);
  // 창이나 사이드바 너비가 바뀌면 기억한 자리로 다시 붙는다
  const observer = new ResizeObserver(() => {
    if (!drag) settle();
  });
  observer.observe(stage);

  const stopLoop = startLoop(
    (dt) => {
      step(X, dt);
      step(Y, dt);
      step(O, dt);
      step(L, dt);
    },
    () => {
      const enter = (1 - clamp(O.x, 0, 1)) * (place.side === "left" ? -8 : 8);
      dock.style.transform = `translate(${(X.x + enter).toFixed(2)}px,${Y.x.toFixed(2)}px) scale(${(1 + 0.04 * L.x).toFixed(4)})`;
      dock.style.opacity = clamp(O.x, 0, 1).toFixed(3);
    },
  );

  return () => {
    stopLoop();
    observer.disconnect();
    dock.removeEventListener("pointerdown", down);
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", up);
  };
}
