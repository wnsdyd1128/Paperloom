/**
 * 쪽 번역 도구 (U7): 번역 줄·글로 읽기 머리·별도 탭 머리가 함께 쓴다. 모든 쪽 번역(본문 없는 쪽 제외, 사용자가 시작·멈춤, D11),
 * 지금 쪽 다시 번역, 번역 글꼴 크기, 닫기. 보기 방식 메뉴(레이아웃 유지·글로 읽기·별도 탭)와 쪽 상태 글도 여기 있다.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { Icon } from "../../shared/Icon";
import { usePreferences } from "../settings/PreferencesProvider";
import type { Language } from "./api";
import type { PageInfo } from "./schedule";
import type { Translation } from "./useTranslation";

export type TranslationMode = "layout" | "reflow" | "tab";

export const LANGUAGE_LABELS: Readonly<Record<Language, string>> = { ko: "한국어", en: "English" };
const FONT = { min: 12, max: 24 }; // 설정의 번역 글꼴 범위 (preferences/models.py)

/** 번역 글꼴 크기: 설정에서 따로 정했으면 그것, 아니면 글꼴 크기보다 조금 크게 */
export function useTranslationFont(): [number, (step: number) => void] {
  const { preferences, save } = usePreferences();
  const size = preferences.translation_font_size ?? Math.min(FONT.max, preferences.font_size + 2);
  return [size, (step) => void save({ translation_font_size: Math.min(FONT.max, Math.max(FONT.min, size + step)) }).catch(() => undefined)];
}

const SCALE = { min: 0.6, max: 1.3, step: 0.1 };
const SCALE_KEY = "paperloom.translation.layout-scale"; // 이 브라우저에서만 기억하는 편의 설정 (A2). 별도 탭과 함께 쓴다
const scaleListeners = new Set<() => void>();
let layoutScale = readScale();

function readScale(): number {
  try {
    const value = Number(localStorage.getItem(SCALE_KEY));
    return value >= SCALE.min && value <= SCALE.max ? value : 1;
  } catch {
    return 1;
  }
}

function subscribeScale(listener: () => void) {
  const fromOtherTab = (event: StorageEvent) => {
    if (event.key !== SCALE_KEY) return;
    layoutScale = readScale();
    listener();
  };
  scaleListeners.add(listener);
  window.addEventListener("storage", fromOtherTab);
  return () => {
    scaleListeners.delete(listener);
    window.removeEventListener("storage", fromOtherTab);
  };
}

/**
 * 레이아웃 유지 번역의 글꼴 배율(원문 글꼴 크기 기준, 1 = 원문과 같게). 문단 상자에 넘치면 그 문단만 더 줄인다.
 * 레이아웃 유지는 원문 여백을 지키므로 px가 아니라 원문 크기의 배율로 바꾼다(2026-10-03 사용자 요청).
 */
export function useLayoutScale(): [number, (step: number) => void] {
  const scale = useSyncExternalStore(subscribeScale, () => layoutScale);
  return [
    scale,
    (step) => {
      layoutScale = Math.round(Math.min(SCALE.max, Math.max(SCALE.min, scale + step * SCALE.step)) * 10) / 10;
      try {
        localStorage.setItem(SCALE_KEY, String(layoutScale));
      } catch {
        // 기억하지 못해도 이번 화면은 바뀐다
      }
      scaleListeners.forEach((listener) => listener());
    },
  ];
}

/** 쪽 하나의 번역 상태 글과 할 수 있는 일 */
export function pageStatus(translation: Translation, pageIndex: number, info: PageInfo | undefined): Readonly<{ text: string; action: "retry" | "translate" | null }> {
  const entry = translation.entries.get(pageIndex);
  if (translation.running === pageIndex) return { text: "번역하는 중…", action: null };
  if (entry?.status === "ready") return { text: `번역함${entry.translation.model ? ` · ${entry.translation.model}` : ""}`, action: null };
  if (entry?.status === "failed") return { text: entry.message, action: entry.code === "NO_TEXT" ? null : "retry" };
  if (info && !info.hasText) return { text: "이 쪽에는 번역할 본문이 없습니다(참고문헌·그림·표·수식뿐이거나 글이 없음).", action: null };
  if (translation.waiting) return { text: "다른 쪽 번역이 끝나면 번역합니다.", action: null };
  if (translation.running !== null) return { text: `${translation.running + 1}쪽을 번역하는 중이라 이어서 번역합니다.`, action: null };
  if (!entry || entry.status === "loading") return { text: "번역을 불러오는 중…", action: null };
  return { text: "번역 전", action: null };
}

type ToolbarProps = Readonly<{
  translation: Translation;
  pageIndex: number;
  pageCount: number;
  /** 글꼴 단추가 바꾸는 것: 레이아웃 유지는 원문 크기 배율(%), 글로 읽기는 px */
  fontMode: "layout" | "text";
  onClose?: () => void;
  /** 별도 탭은 쪽을 앞뒤로 옮긴다 */
  onStep?: (step: number) => void;
}>;

/** 모든 쪽 [시작] · 24 / 29 · 다시 번역 · 글꼴 · 닫기 (2026-10-03 사용자 요청, 시안 "모든 쪽 이어서 번역") */
export function TranslationToolbar({ translation, pageIndex, pageCount, fontMode, onClose, onStep }: ToolbarProps) {
  const { batch, progress, running } = translation;
  const allDone = progress.total > 0 && progress.done >= progress.total;
  return (
    <div className="translation-toolbar" role="toolbar" aria-label="쪽 번역 도구">
      <span className="translation-batch">
        <span className="muted">{batch ? `모든 쪽 번역 중 ${progress.done} / ${progress.total}` : allDone ? "모든 쪽 번역함" : "모든 쪽"}</span>
        {batch ? (
          <button type="button" className="translation-chip is-on" onClick={translation.stopBatch} title="지금 번역하는 쪽까지 하고 멈춥니다">
            멈춤
          </button>
        ) : (
          !allDone && (
            <button type="button" className="translation-chip" onClick={translation.startBatch} title="본문 없는 쪽을 뺀 남은 쪽을 한 쪽씩 번역합니다(쪽마다 구독 사용량을 씁니다. 참고문헌·머리글·수식·표는 번역하지 않습니다)">
              시작
            </button>
          )
        )}
      </span>
      <span className="translation-page">
        {onStep && (
          <button type="button" className="btn btn-icon translation-tool" aria-label="앞 쪽" disabled={pageIndex <= 0} onClick={() => onStep(-1)}>
            <Icon name="chevronUp" size={15} />
          </button>
        )}
        <b>{pageIndex + 1}</b> / {pageCount}
        {onStep && (
          <button type="button" className="btn btn-icon translation-tool" aria-label="다음 쪽" disabled={pageIndex >= pageCount - 1} onClick={() => onStep(1)}>
            <Icon name="chevronDown" size={15} />
          </button>
        )}
      </span>
      <span className="translation-actions">
        <button
          type="button"
          className="btn btn-icon translation-tool"
          aria-label="다시 번역"
          title="이 쪽을 다시 번역합니다"
          disabled={running !== null}
          onClick={() => translation.retranslate(pageIndex)}
        >
          <Icon name="rotate" size={15} />
        </button>
        <button
          type="button"
          className="btn btn-icon translation-tool"
          aria-label="번역 모두 지우기"
          title="이 논문의 번역을 모두 지웁니다"
          disabled={running !== null}
          onClick={() => {
            if (!window.confirm("이 논문의 번역을 모두 지울까요? 보고 있는 쪽은 바로 다시 번역합니다(구독 사용량을 씁니다).")) return;
            translation.clearAll().catch(() => window.alert("번역을 지우지 못했습니다. Paperloom이 켜져 있는지 확인하세요."));
          }}
        >
          <Icon name="trash" size={15} />
        </button>
        {fontMode === "layout" ? <LayoutFontMenu /> : <FontMenu />}
        {onClose && (
          <button type="button" className="btn btn-icon translation-tool" aria-label="번역 닫기" title="번역 닫기" onClick={onClose}>
            <Icon name="x" size={15} />
          </button>
        )}
      </span>
    </div>
  );
}

function FontMenu() {
  const [size, change] = useTranslationFont();
  return <FontStepper value={`${size}px`} atMin={size <= FONT.min} atMax={size >= FONT.max} onStep={change} />;
}

function LayoutFontMenu() {
  const [scale, change] = useLayoutScale();
  return (
    <FontStepper
      value={`${Math.round(scale * 100)}%`}
      atMin={scale <= SCALE.min}
      atMax={scale >= SCALE.max}
      onStep={change}
      note="원문 글자 크기 기준. 문단 자리에 넘치면 그 문단만 줄입니다."
    />
  );
}

function FontStepper({ value, atMin, atMax, onStep, note }: Readonly<{ value: string; atMin: boolean; atMax: boolean; onStep: (step: number) => void; note?: string }>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => !ref.current?.contains(event.target as Node) && setOpen(false);
    document.addEventListener("pointerdown", close, true);
    return () => document.removeEventListener("pointerdown", close, true);
  }, [open]);
  return (
    <span className="translation-font" ref={ref}>
      <button type="button" className="btn btn-icon translation-tool" aria-label="번역 글꼴 크기" aria-expanded={open} title="번역 글꼴 크기" onClick={() => setOpen(!open)}>
        <Icon name="type" size={15} />
      </button>
      {open && (
        <span className="translation-font-menu" role="group" aria-label="번역 글꼴 크기 조절" title={note}>
          <button type="button" className="btn btn-icon translation-tool" aria-label="번역 글꼴 작게" disabled={atMin} onClick={() => onStep(-1)}>
            A−
          </button>
          <span className="translation-font-value">{value}</span>
          <button type="button" className="btn btn-icon translation-tool" aria-label="번역 글꼴 크게" disabled={atMax} onClick={() => onStep(1)}>
            A+
          </button>
        </span>
      )}
    </span>
  );
}

const MODES: readonly Readonly<{ mode: TranslationMode; label: string; note: string; icon: "panel" | "fileText" | "share" }>[] = [
  { mode: "layout", label: "원문과 나란히 · 레이아웃 유지", note: "같은 자리에 번역문을 놓은 쪽을 옆에 둡니다.", icon: "panel" },
  { mode: "reflow", label: "원문과 나란히 · 글로 읽기", note: "번역문만 이어 붙여 큰 글자로 읽습니다.", icon: "fileText" },
  { mode: "tab", label: "별도 브라우저 탭에서 열기", note: "다른 모니터에 번역을 띄울 때. 쪽 이동이 두 탭에서 맞춰집니다.", icon: "share" },
];
export const MODE_LABELS: Readonly<Record<TranslationMode, string>> = { layout: "레이아웃 유지", reflow: "글로 읽기", tab: "별도 탭" };

/** 보기 방식 메뉴 (시안 "번역 보기 방식") */
export function ModeMenu({ mode, onMode }: Readonly<{ mode: TranslationMode; onMode: (mode: TranslationMode) => void }>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => !ref.current?.contains(event.target as Node) && setOpen(false);
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", close, true);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", close, true);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <span className="translation-mode" ref={ref}>
      <button type="button" className="translation-mode-button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        보기 방식 · {MODE_LABELS[mode]}
        <Icon name="chevronDown" size={12} />
      </button>
      {open && (
        <div className="translation-mode-menu" role="menu" aria-label="번역 보기 방식">
          <div className="translation-mode-title">번역 보기 방식</div>
          {MODES.map((item) => (
            <button
              key={item.mode}
              type="button"
              role="menuitemradio"
              aria-checked={item.mode === mode}
              className="translation-mode-item"
              onClick={() => {
                setOpen(false);
                onMode(item.mode);
              }}
            >
              <span className="translation-mode-dot" aria-hidden="true" />
              <Icon name={item.icon} size={16} />
              <span>
                <b>{item.label}</b>
                <span className="muted">{item.note}</span>
              </span>
            </button>
          ))}
          <div className="translation-mode-note">
            번역 글꼴 단추: 레이아웃 유지는 원문 글자 크기 기준 %로, 글로 읽기는 px로 바꿉니다(글로 읽기 크기는 설정 › 화면에도 있습니다).
          </div>
        </div>
      )}
    </span>
  );
}
