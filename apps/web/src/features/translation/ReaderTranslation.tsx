/**
 * Reader의 쪽 번역 보기 (U7, 시안 Reader v3): 번역 줄(본문 위), 레이아웃 유지(원문 쪽 옆의 번역 쪽, 같은 스크롤),
 * 글로 읽기(오른쪽 칸), 별도 탭 안내 줄. 상태와 차례는 useTranslation이 맡는다.
 */
import "./translation.css";

import type { PDFDocumentProxy, PageViewport } from "pdfjs-dist";
import type { PDFViewer } from "pdfjs-dist/web/pdf_viewer.mjs";
import { type RefObject, useCallback, useLayoutEffect, useState } from "react";

import { Icon } from "../../shared/Icon";
import { contentFrame } from "../reader/selection";
import type { Language } from "./api";
import type { LinkedSentence } from "./linkedSentence";
import type { PageInfo } from "./schedule";
import { type PageSize, type SourceHover, TranslatedPage } from "./TranslatedPage";
import { LANGUAGE_LABELS, ModeMenu, MODE_LABELS, pageStatus, type TranslationMode, TranslationToolbar, useTranslationFont } from "./TranslationControls";
import { TranslationText } from "./TranslationText";
import type { Translation } from "./useTranslation";

/** 원문 쪽과 번역 쪽 사이 (레이아웃 유지) */
export const TRANSLATION_GAP = 16;

export type TranslationView = Readonly<{ on: boolean; mode: TranslationMode }>;
const VIEW_KEY = "paperloom.reader.translation"; // 이 브라우저에서만 기억하는 편의 설정 (A2)

/** 쪽 번역 켬과 보기 방식. 처음은 꺼짐·레이아웃 유지 */
export function useTranslationView(): [TranslationView, (view: TranslationView) => void] {
  const [view, setView] = useState<TranslationView>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(VIEW_KEY) ?? "null") as Partial<TranslationView> | null;
      const mode = stored?.mode === "reflow" || stored?.mode === "tab" ? stored.mode : "layout";
      // 별도 탭은 탭을 다시 열어야 하므로 새로 열 때는 이 탭에서 본다
      return { on: stored?.on === true && mode !== "tab", mode: mode === "tab" ? "layout" : mode };
    } catch {
      return { on: false, mode: "layout" };
    }
  });
  const save = useCallback((next: TranslationView) => {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, JSON.stringify(next));
    } catch {
      // 기억하지 못해도 이번 화면은 바뀐다
    }
  }, []);
  return [view, save];
}

type BarProps = Readonly<{
  translation: Translation;
  language: Language;
  mode: TranslationMode;
  pageIndex: number;
  pageCount: number;
  info: PageInfo | undefined;
  onMode: (mode: TranslationMode) => void;
  onClose: () => void;
  onFocusTab: () => void;
}>;

/** 본문 위 번역 줄: "20쪽 번역 · 한국어", 보기 방식, 지금 쪽 상태. 레이아웃 유지면 번역 도구도 여기 있다. */
export function TranslationBar({ translation, language, mode, pageIndex, pageCount, info, onMode, onClose, onFocusTab }: BarProps) {
  if (mode === "tab") {
    return (
      <div className="translation-bar is-tab" role="status">
        <Icon name="share" size={15} />
        <b>번역을 별도 탭에서 보는 중</b>
        <span className="muted">쪽 이동·문장 강조 동기화</span>
        <button type="button" className="btn btn-ghost translation-bar-link" onClick={onFocusTab}>
          번역 탭으로
        </button>
        <button type="button" className="btn btn-plain" onClick={() => onMode("layout")}>
          이 탭에서 보기
        </button>
      </div>
    );
  }
  const status = pageStatus(translation, pageIndex, info);
  return (
    <div className="translation-bar">
      <Icon name="languages" size={15} />
      <b>
        {pageIndex + 1}쪽 번역 · {LANGUAGE_LABELS[language]}
      </b>
      <span className="muted translation-bar-mode">{mode === "reflow" ? "왼쪽 원문 · 오른쪽 번역문(글로 읽기)" : "왼쪽 원문 · 오른쪽 번역 · 함께 스크롤"}</span>
      <span className="translation-bar-status" role="status" data-status={translation.entries.get(pageIndex)?.status ?? "none"}>
        {status.text}
        {status.action && (
          <button type="button" className="btn btn-ghost" disabled={translation.running !== null} onClick={() => translation.translateNow(pageIndex)}>
            {status.action === "retry" ? "다시 시도" : "이 쪽 번역"}
          </button>
        )}
      </span>
      <ModeMenu mode={mode} onMode={onMode} />
      {mode === "layout" && <TranslationToolbar translation={translation} pageIndex={pageIndex} pageCount={pageCount} fontMode="layout" onClose={onClose} />}
      {mode === "reflow" && (
        <button type="button" className="btn btn-icon translation-tool" aria-label="번역 닫기" title={`번역 닫기 (${MODE_LABELS[mode]})`} onClick={onClose}>
          <Icon name="x" size={15} />
        </button>
      )}
    </div>
  );
}

type Placed = Readonly<{ pageIndex: number; left: number; top: number; viewport: PageViewport; size: PageSize }>;

type LayerProps = Readonly<{
  viewer: PDFViewer | null;
  pdfDocument: PDFDocumentProxy;
  scrollRef: RefObject<HTMLDivElement | null>;
  /** 배율·회전·쪽 수가 바뀌면 바뀌는 값(자리를 다시 잰다) */
  layoutKey: string;
  translation: Translation;
  pages: readonly PageInfo[];
  onHover: (hover: SourceHover) => void;
  /** 원문 문장에 마우스를 올린 동안 강조할 번역 문장 */
  linked: LinkedSentence;
}>;

/**
 * 레이아웃 유지: 원문 쪽마다 오른쪽에 같은 크기의 번역 쪽을 둔다. 스크롤 영역 안에 있어 함께 스크롤된다.
 * 원문 쪽은 번역 쪽 자리만큼 왼쪽으로 옮긴다(.pdfViewer 오른쪽 여백 = 번역 쪽 폭 + 사이, 둘이 함께 가운데에 온다).
 * 번역 쪽은 원문 쪽 상자의 실제 크기다: PDF.js는 쪽을 그릴 때 쪽 크기를 화면 픽셀 단위(화면 배율 1.25면 4px)로 내리고, 그래서
 * 그린 쪽이 줄면 아래 쪽들이 올라간다. 쪽 상자 크기가 바뀌면 다시 잰다(2026-10-04 사용자 확인: 100%에서는 맞는데 확대하면 어긋났다).
 * 스크롤 영역의 .is-translating 클래스는 ReaderPage가 className으로 준다(여기서 classList로 바꾸면 영역 모드처럼
 * React가 className을 다시 쓸 때 지워져 원문 쪽이 번역 쪽 아래로 밀렸다, 2026-10-03 사용자 확인). 폭은 CSS 변수로 둔다.
 */
export function TranslationLayer({ viewer, pdfDocument, scrollRef, layoutKey, translation, pages, onHover, linked }: LayerProps) {
  const [placed, setPlaced] = useState<readonly Placed[]>([]);
  const [resized, setResized] = useState(0);

  useLayoutEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => setResized((count) => count + 1));
    observer.observe(container);
    return () => {
      observer.disconnect();
      container.style.removeProperty("--translation-width");
    };
  }, [scrollRef]);

  useLayoutEffect(() => {
    const container = scrollRef.current;
    if (!viewer || !container || viewer.pagesCount === 0) return;
    const views = Array.from({ length: viewer.pagesCount }, (_, index) => viewer.getPageView(index)).filter((view) => view?.div && view.viewport);
    const width = Math.max(...views.map((view) => view.viewport.width));
    container.style.setProperty("--translation-width", `${width}px`);
    const frame = container.getBoundingClientRect();
    setPlaced(
      views.map((view) => {
        const page = contentFrame(view.div);
        return {
          pageIndex: view.id - 1,
          left: page.left + page.width - frame.left + container.scrollLeft + TRANSLATION_GAP,
          top: page.top - frame.top + container.scrollTop,
          viewport: view.viewport,
          size: { width: page.width, height: page.height },
        };
      }),
    );
    // 원문 쪽 상자 크기가 바뀌면(그릴 때 화면 픽셀 단위로 내림) 다시 잰다. 크기가 같으면 ResizeObserver는 알리지 않는다
    let first = true;
    const observer = new ResizeObserver(() => {
      if (first) first = false; // 지켜보기 시작할 때 한 번 알린다
      else setResized((count) => count + 1);
    });
    for (const view of views) observer.observe(view.div);
    return () => observer.disconnect();
  }, [viewer, scrollRef, layoutKey, resized]);

  const load = useCallback((pageIndex: number) => !translation.entries.has(pageIndex) && void translation.load(pageIndex), [translation]);
  return (
    <div className="translation-layer" aria-label="번역 쪽">
      {placed.map((item) => (
        <div key={item.pageIndex} className="translation-slot" style={{ left: item.left, top: item.top }}>
          <TranslatedPage
            pdfDocument={pdfDocument}
            pageIndex={item.pageIndex}
            viewport={item.viewport}
            size={item.size}
            entry={translation.entries.get(item.pageIndex)}
            root={scrollRef}
            onVisible={load}
            onHover={onHover}
            linked={linked}
            message={translation.entries.get(item.pageIndex)?.status === "ready" ? null : pageStatus(translation, item.pageIndex, pages[item.pageIndex]).text}
          />
        </div>
      ))}
    </div>
  );
}

type ReflowProps = Readonly<{
  translation: Translation;
  pageIndex: number;
  pageCount: number;
  info: PageInfo | undefined;
  onClose: () => void;
  onHover: (hover: SourceHover) => void;
  linked: LinkedSentence;
}>;

/** 글로 읽기: 본문 오른쪽 칸에 지금 쪽의 번역문 (머리에 번역 도구) */
export function ReflowPanel({ translation, pageIndex, pageCount, info, onClose, onHover, linked }: ReflowProps) {
  const [fontSize] = useTranslationFont();
  return (
    <aside className="translation-reflow" aria-label="번역문">
      <TranslationToolbar translation={translation} pageIndex={pageIndex} pageCount={pageCount} fontMode="text" onClose={onClose} />
      <div className="translation-reflow-body">
        <TranslationText
          pageIndex={pageIndex}
          entry={translation.entries.get(pageIndex)}
          fontSize={fontSize}
          status={pageStatus(translation, pageIndex, info).text}
          onHover={onHover}
          linked={linked}
        />
      </div>
    </aside>
  );
}
