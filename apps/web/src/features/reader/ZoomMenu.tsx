import { useEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";
import { formatZoom, ZOOM_PRESETS } from "./zoom";

type Props = Readonly<{
  zoom: number;
  rotation: number;
  disabled: boolean;
  onZoom: (scale: number) => void;
  onRotate: () => void;
}>;

/**
 * 머리의 배율 칸 (시안 "자동" 칸). 누르면 배율 목록과 시계 방향 회전이 나온다(회전은 PLAN §6 필수 기능, A6).
 * 휠로 만든 목록 밖의 배율도 지금 값으로 보인다. 바깥을 누르거나 Esc로 닫는다.
 */
export function ZoomMenu({ zoom, rotation, disabled, onZoom, onRotate }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      ref.current?.querySelector<HTMLButtonElement>(".zoom-button")?.focus(); // 키보드 사용자가 제자리로 돌아온다
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus();
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const choose = (scale: number) => {
    onZoom(scale);
    setOpen(false);
  };
  const values = ZOOM_PRESETS.includes(zoom) ? ZOOM_PRESETS : [...ZOOM_PRESETS, zoom].sort((a, b) => a - b);
  return (
    <div className="zoom-menu" ref={ref}>
      <button
        type="button"
        className="head-box zoom-button"
        aria-label="배율"
        aria-haspopup="menu"
        aria-expanded={open}
        data-zoom={zoom}
        data-rotation={rotation}
        title="배율·회전"
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      >
        <span>
          {formatZoom(zoom)}
          {rotation !== 0 && ` · ${rotation}°`}
        </span>
        <Icon name="chevronDown" size={13} />
      </button>
      {open && (
        <div className="menu-popover zoom-list" role="menu" aria-label="배율">
          {values.map((value) => (
            <button key={value} type="button" role="menuitemradio" aria-checked={value === zoom} onClick={() => choose(value)}>
              {formatZoom(value)}
            </button>
          ))}
          <span className="menu-rule" role="separator" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onRotate();
              setOpen(false);
            }}
          >
            <Icon name="rotate" size={14} />
            시계 방향으로 회전
            <span className="menu-meta">{rotation}°</span>
          </button>
        </div>
      )}
    </div>
  );
}
