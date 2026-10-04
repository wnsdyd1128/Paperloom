import { type PointerEvent, useEffect, useLayoutEffect, useRef, useState } from "react";

import { Icon, type IconName } from "../../shared/Icon";
import { leaderLine, type Offset, toPageUnits, toPixels } from "./chipGeometry";
import type { Placed, Spot } from "./InlineLayer";

/** 본문 옆 칩 하나: 접은 선택 설명·질문 대화, 메모가 있는 주석 */
export type MarginChip = Readonly<{
  /** 옮긴 자리를 기억하는 키. 새로고침해도 같은 것(대화 ID·주석 ID) */
  id: string;
  icon: IconName;
  title: string;
  meta?: string;
  /** 누르면 하는 일 (마우스를 올리면 보인다) */
  hint: string;
  spot: Spot;
  className: string;
  /** data-* 속성 (시험·다른 화면이 칩을 찾는다) */
  data: Readonly<Record<string, string>>;
  onOpen: () => void;
}>;

type Props = Readonly<{
  chips: readonly MarginChip[];
  place: (spot: Spot) => Placed | null;
  /** 옮긴 자리를 이 브라우저에 기억하는 키(논문마다) */
  storageKey: string;
}>;

const CHIP_HEIGHT = 30;
const INSET = 52; // 시안 3i: 쪽 오른쪽 끝에서 안쪽으로
const CLICK_SLOP = 6; // px. 이보다 덜 움직이고 떼면 누름이다

/**
 * 본문 옆 칩들 (2026-10-02 사용자 요청). 쪽 오른쪽 끝, 고른 줄 높이에 두고 겹치면 아래로 민다. 칩은 끌어 옮길 수 있고,
 * 고른 곳까지 옅은 선을 긋는다. 마우스를 올리거나 끄는 동안 선이 진해지고 고른 곳에 테두리를 그린다.
 */
export function MarginChips({ chips, place, storageKey }: Props) {
  const [offsets, setOffset] = useOffsets(storageKey);
  let lastBottom = -Infinity;
  const stacked = chips
    .map((chip) => ({ chip, placed: place(chip.spot) }))
    .filter((item): item is { chip: MarginChip; placed: Placed } => item.placed !== null)
    .sort((a, b) => a.placed.top - b.placed.top)
    .map((item) => {
      const top = Math.max(item.placed.top, lastBottom + 4);
      lastBottom = top + CHIP_HEIGHT;
      return { ...item, top };
    });
  return (
    <>
      {stacked.map(({ chip, placed, top }) => (
        <Chip key={chip.id} chip={chip} placed={placed} top={top} units={offsets[chip.id]} onMoved={(units) => setOffset(chip.id, units)} />
      ))}
    </>
  );
}

function Chip({ chip, placed, top, units, onMoved }: { chip: MarginChip; placed: Placed; top: number; units: Offset | undefined; onMoved: (units: Offset) => void }) {
  const pageWidth = placed.pageRight - placed.pageLeft;
  const [drag, setDrag] = useState<Offset | null>(null); // 끄는 중인 옮김(px)
  const [active, setActive] = useState(false); // 마우스를 올렸거나 포커스가 있다
  const [width, setWidth] = useState(0);
  const ref = useRef<HTMLButtonElement>(null);
  const dragged = useRef(false);
  useLayoutEffect(() => {
    const measured = ref.current?.offsetWidth ?? 0;
    if (measured !== width) setWidth(measured);
  });
  const offset = drag ?? toPixels(units, pageWidth);
  const right = placed.pageRight - INSET + offset.x; // 칩의 오른쪽 끝
  const box = { left: right - width, top: top + offset.y, width, height: CHIP_HEIGHT };
  const line = leaderLine(placed, box);
  const highlighted = active || drag !== null;

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    const button = event.currentTarget;
    const origin = { x: event.clientX, y: event.clientY };
    const start = toPixels(units, pageWidth);
    const at = (next: globalThis.PointerEvent) => ({ x: start.x + next.clientX - origin.x, y: start.y + next.clientY - origin.y });
    dragged.current = false;
    button.setPointerCapture(event.pointerId);
    const move = (next: globalThis.PointerEvent) => {
      if (!dragged.current && Math.hypot(next.clientX - origin.x, next.clientY - origin.y) < CLICK_SLOP) return;
      dragged.current = true;
      setDrag(at(next));
    };
    const end = (last: globalThis.PointerEvent) => {
      button.removeEventListener("pointermove", move);
      button.removeEventListener("pointerup", end);
      button.removeEventListener("pointercancel", end);
      if (!dragged.current) return;
      onMoved(toPageUnits(at(last), pageWidth));
      setDrag(null);
    };
    button.addEventListener("pointermove", move);
    button.addEventListener("pointerup", end);
    button.addEventListener("pointercancel", end);
  }

  const data = Object.fromEntries(Object.entries(chip.data).map(([name, value]) => [`data-${name}`, value]));
  return (
    <>
      {line && width > 0 && (
        <svg className={highlighted ? "chip-leader is-active" : "chip-leader"} aria-hidden="true">
          <line x1={line.x1} y1={line.y1} x2={line.x2} y2={line.y2} />
        </svg>
      )}
      {highlighted && (
        <span
          className="chip-anchor-box"
          style={{ left: placed.left - 3, top: placed.top - 3, width: placed.right - placed.left + 6, height: placed.bottom - placed.top + 6 }}
          aria-hidden="true"
        />
      )}
      <button
        ref={ref}
        type="button"
        className={chip.className}
        style={{ top: box.top, left: right, transform: "translateX(-100%)" }}
        title={`${chip.hint} · 끌어서 옮기기`}
        onPointerDown={onPointerDown}
        onClick={() => {
          if (dragged.current) {
            dragged.current = false; // 끈 것은 누름이 아니다
            return;
          }
          chip.onOpen();
        }}
        onMouseEnter={() => setActive(true)}
        onMouseLeave={() => setActive(false)}
        onFocus={() => setActive(true)}
        onBlur={() => setActive(false)}
        {...data}
      >
        <Icon name={chip.icon} size={13} className="thread-chip-icon" />
        <span className="thread-chip-title">{chip.title}</span>
        {chip.meta && <span className="thread-chip-meta">{chip.meta}</span>}
        <Icon name="expand" size={13} />
      </button>
    </>
  );
}

/** 칩마다 옮긴 자리(쪽 너비 비율). 이 브라우저에만 기억한다(편의 설정). */
function useOffsets(storageKey: string) {
  const [offsets, setOffsets] = useState<Readonly<Record<string, Offset>>>(() => read(storageKey));
  useEffect(() => setOffsets(read(storageKey)), [storageKey]);
  const set = (id: string, units: Offset) =>
    setOffsets((current) => {
      const next = { ...current, [id]: units };
      try {
        localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        // 기억하지 못해도 이번 화면에서는 옮겨진다
      }
      return next;
    });
  return [offsets, set] as const;
}

function read(storageKey: string): Readonly<Record<string, Offset>> {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) ?? "{}") as unknown;
    return value && typeof value === "object" ? (value as Record<string, Offset>) : {};
  } catch {
    return {};
  }
}
