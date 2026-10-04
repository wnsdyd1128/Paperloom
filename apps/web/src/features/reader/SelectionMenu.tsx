import { type MouseEvent, useEffect, useLayoutEffect, useRef, useState } from "react";

import { Icon, type IconName } from "../../shared/Icon";
import { type HighlightColor, REGION_KIND_LABELS, type RegionKind } from "../annotations/api";
import { HIGHLIGHT_COLOR_LABELS, HIGHLIGHT_COLORS } from "../annotations/highlights";
import { isEditable } from "./clipboard";
import type { CssRect } from "./geometry";

/** 선택 메뉴의 동작. note는 메모 창, ask는 질문 창을 연다 (docs/UI_PLAN.md U2). */
export type MenuAction = "explain" | "translate" | "highlight" | "note" | "ask" | "copy";

type Item = Readonly<{ action: MenuAction; label: string; icon: IconName; key: string; code: string; hint: string }>;

const TEXT_ITEMS: readonly Item[] = [
  { action: "explain", label: "설명", icon: "sparkles", key: "E", code: "KeyE", hint: "Claude가 이 부분을 설명합니다" },
  { action: "translate", label: "번역", icon: "languages", key: "T", code: "KeyT", hint: "Claude가 이 부분을 번역합니다" },
  { action: "highlight", label: "하이라이트", icon: "highlighter", key: "H", code: "KeyH", hint: "마지막에 고른 색으로 칠해 둡니다" },
  { action: "note", label: "주석", icon: "note", key: "C", code: "KeyC", hint: "메모를 달아 주석으로 저장합니다" },
];
const ASK_ITEM: Item = { action: "ask", label: "AI에게 질문", icon: "ask", key: "Enter", code: "Enter", hint: "이 부분을 두고 직접 묻습니다" };
const REGION_KINDS_SHOWN: readonly RegionKind[] = ["figure", "table", "equation"];
const GAP = 8;

type Props = Readonly<{
  kind: "text" | "region";
  /** 한 쪽 안의 선택만 저장·질문할 수 있다. 아니면 이유를 보인다. */
  blockedReason: string | null;
  /** 영역 종류(그림·표·수식). 고른 종류로 저장하고 묻는다. */
  regionKind: RegionKind;
  onRegionKind: (kind: RegionKind) => void;
  /** 선택을 감싸는 화면 사각형. 화면 밖이면 null */
  getRect: () => CssRect | null;
  /** 스크롤하면 위치를 다시 잰다 */
  scrollContainer: HTMLElement | null;
  busy: boolean;
  /** 하이라이트는 고른 색(견본)으로, 없으면(H·줄 누르기) 마지막에 고른 색으로 칠한다 (U5). */
  onAction: (action: MenuAction, color?: HighlightColor) => void;
  onClose: () => void;
}>;

/**
 * 글·영역을 고르면 그 곁에 뜨는 메뉴 (시안 Reader v3의 선택 메뉴·영역 도구줄).
 * - 글: 세로 메뉴. 설명 E · 번역 T · 하이라이트 H(색 견본 셋, U5) · 주석 C · AI에게 질문 Enter
 * - 영역: 가로 도구줄. 종류(그림·표·수식) · 설명 E · AI에게 질문 · 주석 · 그림 복사 Ctrl+C
 * 단축키는 메뉴가 떠 있고 글 쓰는 칸에 있지 않을 때만 받는다. 한글 입력 상태도 같은 물리 키로 받는다.
 * 바깥을 누르거나 Esc로 닫는다.
 */
export function SelectionMenu({ kind, blockedReason, regionKind, onRegionKind, getRect, scrollContainer, busy, onAction, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  const place = () => {
    const rect = getRect();
    const element = ref.current;
    const view = scrollContainer?.getBoundingClientRect();
    let next: { left: number; top: number } | null = null;
    if (rect && element && view && rect.bottom >= view.top && rect.top <= view.bottom) {
      const { width, height } = element.getBoundingClientRect();
      // 고른 것 아래에 두고, 자리가 없으면 위에 둔다. 글 메뉴는 고른 끝(오른쪽)에, 영역 도구줄은 왼쪽에 맞춘다.
      const below = rect.bottom + GAP;
      const top = below + height <= view.bottom ? below : Math.max(view.top + 4, rect.top - height - GAP);
      const left = kind === "text" ? rect.right - width : rect.left;
      next = { left: Math.round(Math.max(view.left + 4, Math.min(left, view.right - width - 4))), top: Math.round(top) };
    }
    // 매 렌더마다 다시 재므로 값이 같으면 상태를 바꾸지 않는다(바꾸면 렌더가 끝없이 돈다).
    setPosition((current) => (current?.left === next?.left && current?.top === next?.top ? current : next));
  };

  useLayoutEffect(place);

  useEffect(() => {
    let frame = 0;
    const later = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    const items = kind === "text" ? [...TEXT_ITEMS, ASK_ITEM] : REGION_SHORTCUTS;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (blockedReason || busy || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return;
      // 글 쓰는 칸, 그리고 단추·링크에 포커스가 있으면(Enter가 그것을 누른다) 단축키로 보지 않는다.
      const active = document.activeElement;
      if (isEditable(active) || active instanceof HTMLButtonElement || active instanceof HTMLAnchorElement) return;
      const item = items.find((candidate) => candidate.code === event.code);
      if (!item) return;
      event.preventDefault();
      onAction(item.action);
    };
    scrollContainer?.addEventListener("scroll", later, { passive: true });
    window.addEventListener("resize", later);
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(frame);
      scrollContainer?.removeEventListener("scroll", later);
      window.removeEventListener("resize", later);
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [scrollContainer, getRect, onClose, onAction, kind, blockedReason, busy]);

  const style = position ? { left: position.left, top: position.top } : { visibility: "hidden" as const, left: 0, top: 0 };
  // 메뉴를 눌러도 글 선택과 포커스가 그대로 남게 한다.
  const keepSelection = (event: MouseEvent) => event.preventDefault();

  if (kind === "text") {
    return (
      <div ref={ref} className="selection-menu" role="menu" aria-label="고른 글로 할 일" style={style} onMouseDown={keepSelection}>
        {blockedReason ? (
          <p className="selection-menu-note">{blockedReason}</p>
        ) : (
          <>
            {TEXT_ITEMS.map((item) =>
              item.action === "highlight" ? (
                <div key={item.action} className="selection-menu-highlight">
                  <MenuItem item={item} busy={busy} onAction={onAction} />
                  <span className="highlight-swatches">
                    {HIGHLIGHT_COLORS.map((color) => (
                      <button
                        key={color}
                        type="button"
                        role="menuitem"
                        className="color-swatch"
                        data-color={color}
                        aria-label={`하이라이트: ${HIGHLIGHT_COLOR_LABELS[color]}`}
                        title={HIGHLIGHT_COLOR_LABELS[color]}
                        disabled={busy}
                        onClick={() => onAction("highlight", color)}
                      />
                    ))}
                  </span>
                </div>
              ) : (
                <MenuItem key={item.action} item={item} busy={busy} onAction={onAction} />
              ),
            )}
            <span className="selection-menu-rule" role="separator" />
            <MenuItem item={ASK_ITEM} busy={busy} onAction={onAction} />
          </>
        )}
      </div>
    );
  }
  return (
    <div ref={ref} className="region-toolbar" role="toolbar" aria-label="고른 영역으로 할 일" style={style} onMouseDown={keepSelection}>
      <div className="seg" role="radiogroup" aria-label="영역 종류">
        {REGION_KINDS_SHOWN.map((value) => (
          <label key={value} className="seg-opt">
            <input type="radio" name="region-kind" checked={regionKind === value} onChange={() => onRegionKind(value)} />
            {REGION_KIND_LABELS[value]}
          </label>
        ))}
      </div>
      <button type="button" className="region-tool is-primary" disabled={busy} onClick={() => onAction("explain")} title="Claude가 이 영역을 설명합니다">
        <Icon name="sparkles" size={14} />
        설명 <span className="kbd">E</span>
      </button>
      <button type="button" className="region-tool" disabled={busy} onClick={() => onAction("ask")} title="이 영역을 두고 직접 묻습니다">
        <Icon name="ask" size={14} />
        AI에게 질문
      </button>
      <button type="button" className="region-tool" disabled={busy} onClick={() => onAction("note")} title="메모를 달아 주석으로 저장합니다">
        <Icon name="note" size={14} />
        주석
      </button>
      <button type="button" className="region-tool" disabled={busy} onClick={() => onAction("copy")} title="이미지로 클립보드에 복사합니다">
        <Icon name="copy" size={14} />
        그림 복사 <span className="kbd">Ctrl+C</span>
      </button>
    </div>
  );
}

const REGION_SHORTCUTS: readonly Pick<Item, "action" | "code">[] = [{ action: "explain", code: "KeyE" }];

function MenuItem({ item, busy, onAction }: { item: Item; busy: boolean; onAction: (action: MenuAction) => void }) {
  return (
    <button type="button" role="menuitem" className="selection-menu-item" disabled={busy} title={item.hint} onClick={() => onAction(item.action)}>
      <Icon name={item.icon} size={15} />
      <span className="selection-menu-label">{item.label}</span>
      <span className="kbd" aria-hidden="true">
        {item.key}
      </span>
    </button>
  );
}
