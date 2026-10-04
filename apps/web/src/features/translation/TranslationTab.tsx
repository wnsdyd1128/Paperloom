/**
 * 별도 브라우저 탭의 쪽 번역 (U7, 시안 Translation Tab): `/reader/{paper}/translation?version=&page=`. 다른 모니터에 번역을
 * 띄울 때 쓴다. 모든 쪽을 이어 스크롤하고(마우스 휠로 쪽을 넘긴다, 2026-10-03 사용자 요청), 스크롤로 바뀐 지금 쪽을 원문
 * 탭과 맞춘다(channel). 문장에 마우스를 올리면 원문 탭이 그 원문 문장을 강조한다. 레이아웃 유지는 Ctrl+휠·Ctrl+±/0으로
 * 번역 쪽만 확대한다(원문 Reader와 같은 단계, 2026-10-03 사용자 확인: 브라우저 확대는 쪽이 창 폭에 다시 맞춰져 커지지 않았다).
 * 번역 차례(지금 쪽·모든 쪽 번역)는 이 탭이 맡는다(원문 탭은 별도 탭 보기에서 번역하지 않는다).
 */
import "./translation.css";

import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { type RefObject, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { Route } from "../../app/route";
import { Icon } from "../../shared/Icon";
import { useBridge } from "../chat/BridgeStatus";
import { getPaper, listPageTexts, type PageTexts, type Paper, sourcePdfUrl } from "../library/api";
import { loadPdfJs } from "../reader/pdfjs";
import { createZoomPinner, DEFAULT_ZOOM, normalizeZoom, stepZoom, wheelZoomFactor, zoomKeyAction } from "../reader/zoom";
import { usePreferences } from "../settings/PreferencesProvider";
import { openTranslationChannel, pageInfos, scrollDelta, type TranslationChannel, viewPosition } from "./channel";
import type { LinkedSentence } from "./linkedSentence";
import type { PageInfo } from "./schedule";
import { type SourceHover, TranslatedPage, useInView } from "./TranslatedPage";
import { LANGUAGE_LABELS, pageStatus, TranslationToolbar, useTranslationFont } from "./TranslationControls";
import { TranslationText } from "./TranslationText";
import { type Translation, useTranslation } from "./useTranslation";

type TabRoute = Extract<Route, { kind: "translation" }>;
type Mode = "layout" | "reflow";
const MODE_KEY = "paperloom.translation-tab.mode"; // 이 브라우저에서만 기억하는 편의 설정
const PAGE_WIDTH = 860;
const PAGE_GAP = 16; // 쪽으로 옮길 때 쪽 위 여백

function storedMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === "reflow" ? "reflow" : "layout";
  } catch {
    return "layout";
  }
}

/** 스크롤 영역 위 1/3 줄에 걸친 쪽(그 줄보다 위에서 시작한 마지막 쪽). 원문 Reader의 읽는 줄과 같다. */
function pageInView(main: HTMLElement): number {
  const line = main.getBoundingClientRect().top + main.clientHeight / 3;
  let page = 0;
  for (const section of main.querySelectorAll<HTMLElement>("[data-tab-page]")) {
    if (section.getBoundingClientRect().top > line) break;
    page = Number(section.dataset.tabPage);
  }
  return page;
}

export function TranslationTab({ route, navigate }: Readonly<{ route: TabRoute; navigate: (route: Route, options?: { replace?: boolean }) => void }>) {
  const [paper, setPaper] = useState<Paper | null>(null);
  const [failed, setFailed] = useState(false);
  const [texts, setTexts] = useState<PageTexts | null>(null);
  const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null);
  const [pdfPages, setPdfPages] = useState<readonly PDFPageProxy[] | null>(null);
  const [frameWidth, setFrameWidth] = useState(() => window.innerWidth);
  const [zoom, setZoom] = useState(DEFAULT_ZOOM); // 레이아웃 유지 쪽 배율(1 = 창 폭에 맞춘 크기)
  const restorePinRef = useRef<(() => void) | null>(null); // 확대한 뒤 커서 아래 자리를 되돌린다
  const [mode, setMode] = useState<Mode>(storedMode);
  const [connected, setConnected] = useState(false);
  const [linked, setLinked] = useState<LinkedSentence>(null); // 원문 탭에서 마우스를 올린 원문 문장의 번역
  const channelRef = useRef<TranslationChannel | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  const currentRef = useRef(route.page - 1);
  const pinnedRef = useRef<number | null>(null); // 쪽으로 옮긴 scrollTop. 사용자가 스크롤하기 전까지는 지금 쪽을 다시 재지 않는다
  const { preferences } = usePreferences();
  const bridge = useBridge();
  const versionId = route.versionId ?? paper?.current_version.version_id ?? null;
  const pageIndex = route.page - 1;
  const pageCount = paper?.current_version.page_count ?? texts?.pages.length ?? 0;

  useEffect(() => {
    getPaper(route.paperId).then(setPaper, () => setFailed(true));
  }, [route.paperId]);

  useEffect(() => {
    if (!versionId) return;
    listPageTexts(versionId).then(setTexts, () => setTexts(null));
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    void loadPdfJs()
      .then(({ pdfjsLib }) => pdfjsLib.getDocument({ url: sourcePdfUrl(versionId) }).promise)
      .then((document) => {
        loaded = document;
        if (!cancelled) setPdfDocument(document);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      void loaded?.destroy();
    };
  }, [versionId]);

  // 레이아웃 유지 쪽 크기: 창 폭에 맞춘 크기 × 배율(창 크기·배율이 바뀌면 바로 다시 잰다)
  useEffect(() => {
    if (!pdfDocument) return;
    let cancelled = false;
    void Promise.all(Array.from({ length: pdfDocument.numPages }, (_, index) => pdfDocument.getPage(index + 1))).then(
      (pages) => !cancelled && setPdfPages(pages),
    );
    return () => {
      cancelled = true;
    };
  }, [pdfDocument]);
  useEffect(() => {
    const resize = () => setFrameWidth(window.innerWidth);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  const viewports = useMemo(() => {
    const width = Math.min(PAGE_WIDTH, frameWidth - 48) * zoom;
    return pdfPages?.map((page) => page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width })) ?? null;
  }, [pdfPages, frameWidth, zoom]);

  // Ctrl+휠(트랙패드 핀치 포함)·Ctrl+±/0: 레이아웃 유지의 번역 쪽만 확대한다. 글로 읽기는 브라우저 자체 확대로 둔다(글이 다시 흐른다).
  useEffect(() => {
    const main = mainRef.current;
    if (!main || mode !== "layout") return;
    const pinner = createZoomPinner(main, ".translated-page");
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      restorePinRef.current = pinner.pin(event.clientX, event.clientY);
      setZoom((value) => normalizeZoom(value * wheelZoomFactor(event.deltaY, event.deltaMode)));
    };
    const onKeyDown = (event: KeyboardEvent) => {
      const action = zoomKeyAction(event);
      if (!action) return;
      event.preventDefault();
      const frame = main.getBoundingClientRect();
      restorePinRef.current = pinner.pin(frame.left + frame.width / 2, frame.top + frame.height / 3);
      setZoom((value) => (action === "reset" ? DEFAULT_ZOOM : stepZoom(value, action === "in" ? 1 : -1)));
    };
    main.addEventListener("wheel", onWheel, { passive: false });
    document.addEventListener("keydown", onKeyDown);
    return () => {
      main.removeEventListener("wheel", onWheel);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [mode]);
  useLayoutEffect(() => {
    restorePinRef.current?.();
    restorePinRef.current = null;
  }, [viewports]);

  /** 그 쪽 위로 스크롤한다(지금 쪽을 그 쪽으로 두고, 이 스크롤로는 다시 재지 않는다). */
  const scrollToPage = useCallback((page: number) => {
    currentRef.current = page;
    const main = mainRef.current;
    const section = main?.querySelector(`[data-tab-page="${page}"]`);
    if (!main || !section) return;
    main.scrollTop += section.getBoundingClientRect().top - main.getBoundingClientRect().top - PAGE_GAP;
    pinnedRef.current = main.scrollTop;
  }, []);

  /** 레이아웃 유지: 위끝의 쪽 안 자리를 원문 탭에 알린다(원문 탭이 같은 자리를 위끝에 둔다) */
  const postScroll = () => {
    const main = mainRef.current;
    if (!main || mode !== "layout") return;
    const frames = Array.from(main.querySelectorAll<HTMLElement>(".translated-page"), (element) => element.getBoundingClientRect());
    channelRef.current?.post({ type: "scroll", ...viewPosition(main.getBoundingClientRect().top, frames) });
  };
  /** 원문 탭이 알린 쪽 안 자리를 위끝에 둔다(이 스크롤은 되돌려 보내지 않는다) */
  const scrollToPosition = (index: number, offset: number) => {
    const main = mainRef.current;
    const element = main?.querySelector(`.translated-page[data-page-index="${index}"]`);
    if (!main || !element) return goTo(index, false);
    main.scrollTop += scrollDelta(main.getBoundingClientRect().top, element.getBoundingClientRect(), offset);
    pinnedRef.current = main.scrollTop;
    const page = pageInView(main);
    if (page === currentRef.current) return;
    currentRef.current = page;
    navigate({ ...route, page: page + 1 }, { replace: true });
  };

  // 원문 탭과 쪽 이동을 맞춘다(레이아웃 유지는 쪽 안 자리까지)
  const goTo = (index: number, announce: boolean) => {
    const page = Math.min(Math.max(index, 0), Math.max(pageCount - 1, 0));
    navigate({ ...route, page: page + 1 }, { replace: true });
    scrollToPage(page);
    if (!announce) return;
    if (mode === "layout") postScroll();
    else channelRef.current?.post({ type: "page", pageIndex: page });
  };
  const goToRef = useRef(goTo);
  goToRef.current = goTo;
  const scrollToPositionRef = useRef(scrollToPosition);
  scrollToPositionRef.current = scrollToPosition;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  useEffect(() => {
    if (!versionId) return;
    const channel = openTranslationChannel(versionId, (message) => {
      if (message.type === "linked") return setLinked(message.linked);
      if (message.type !== "page" && message.type !== "scroll") return;
      setConnected(true);
      if (modeRef.current === "layout") {
        if (message.type === "scroll") scrollToPositionRef.current(message.pageIndex, message.offset);
      } else if (message.type === "page" && message.pageIndex !== currentRef.current) goToRef.current(message.pageIndex, false);
    });
    channelRef.current = channel;
    channel.post({ type: "hello" });
    return () => channel.close();
  }, [versionId]);

  // 쪽들이 놓이면(처음·보기 방식·창 크기가 바뀌면) 지금 쪽으로. 확대는 커서 아래 자리를 지키므로 옮기지 않는다
  const laidOut = mode === "layout" ? viewports !== null : pageCount > 0;
  useLayoutEffect(() => {
    if (laidOut) scrollToPage(currentRef.current);
  }, [laidOut, mode, frameWidth, scrollToPage]);

  /** 사용자가 스크롤하면 원문 탭에 알린다(레이아웃 유지는 쪽 안 자리, 글로 읽기는 쪽이 바뀔 때). 지금 쪽이 바뀌면 주소도 바꾼다. */
  const onScroll = () => {
    const main = mainRef.current!;
    if (pinnedRef.current !== null && Math.abs(main.scrollTop - pinnedRef.current) < 2) return;
    pinnedRef.current = null;
    postScroll();
    const page = pageInView(main);
    if (page === currentRef.current) return;
    currentRef.current = page;
    navigate({ ...route, page: page + 1 }, { replace: true });
    if (mode !== "layout") channelRef.current?.post({ type: "page", pageIndex: page });
  };

  const pages = useMemo(() => pageInfos(texts?.pages ?? []), [texts]);
  const translation = useTranslation({
    versionId: versionId ?? "",
    language: preferences.answer_language,
    bridge,
    pages,
    current: pageIndex,
    active: versionId !== null,
  });
  const load = useCallback((page: number) => !translation.entries.has(page) && void translation.load(page), [translation]);
  // 번역이 있는(바뀐) 쪽을 원문 탭에 알린다: 원문 탭은 번역을 이 탭에 맡겨 저장된 쪽 목록이 처음 그대로다(원문 → 번역 강조에
  // 그 번역을 다시 읽는다). 다시 번역하거나 모두 지운 뒤 번역하면 저장 시각이 바뀌어 다시 알린다
  const announced = useRef(new Map<number, string>());
  useEffect(() => {
    for (const [page, entry] of translation.entries) {
      if (entry.status !== "ready" || announced.current.get(page) === entry.translation.created_at) continue;
      announced.current.set(page, entry.translation.created_at);
      channelRef.current?.post({ type: "translated", pageIndex: page });
    }
  }, [translation.entries]);
  const hover = useCallback((value: SourceHover) => channelRef.current?.post({ type: "hover", hover: value }), []);
  const status = pageStatus(translation, pageIndex, pages[pageIndex]);

  if (failed) return <p className="status error">논문을 열지 못했습니다. 주소와 백엔드 연결을 확인하세요.</p>;
  return (
    <div className="translation-tab">
      <header className="translation-tab-head">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Paperloom</span>
          <span className="translation-tab-kind">번역</span>
        </span>
        <h1 className="translation-tab-title" title={paper?.title}>
          {paper?.title ?? "논문을 불러오는 중…"}
        </h1>
        <div className="seg" role="radiogroup" aria-label="번역 보기 방식">
          {(["layout", "reflow"] as const).map((item) => (
            <label key={item} className="seg-opt">
              <input
                type="radio"
                name="translation-tab-mode"
                checked={mode === item}
                onChange={() => {
                  setMode(item);
                  try {
                    localStorage.setItem(MODE_KEY, item);
                  } catch {
                    // 기억하지 못해도 이번 화면은 바뀐다
                  }
                }}
              />
              {item === "layout" ? "레이아웃 유지" : "글로 읽기"}
            </label>
          ))}
        </div>
        <span className="translation-tab-link" data-connected={connected}>
          <span className="bridge-dot" aria-hidden="true" />
          {connected ? "원문 탭과 연결됨 · 쪽 이동 동기화" : "원문 탭을 찾는 중"}
        </span>
        <button type="button" className="btn btn-secondary" onClick={() => window.opener?.focus()} disabled={!window.opener}>
          원문 탭으로
        </button>
      </header>
      <div className="translation-tab-tools">
        <span className="translation-tab-language">
          <Icon name="languages" size={15} />
          {pageIndex + 1}쪽 번역 · {LANGUAGE_LABELS[preferences.answer_language]}
        </span>
        <span className="translation-bar-status" role="status" data-status={translation.entries.get(pageIndex)?.status ?? "none"}>
          {status.text}
          {status.action && (
            <button type="button" className="btn btn-ghost" disabled={translation.running !== null} onClick={() => translation.translateNow(pageIndex)}>
              {status.action === "retry" ? "다시 시도" : "이 쪽 번역"}
            </button>
          )}
        </span>
        <TranslationToolbar
          translation={translation}
          pageIndex={pageIndex}
          pageCount={pageCount}
          fontMode={mode === "layout" ? "layout" : "text"}
          onStep={(step) => goTo(pageIndex + step, true)}
        />
      </div>
      <main className="translation-tab-body" ref={mainRef} onScroll={onScroll} data-mode={mode}>
        {mode === "layout"
          ? pdfDocument &&
            viewports?.map((viewport, index) => (
              <section key={index} className="translation-tab-page" data-tab-page={index} aria-label={`${index + 1}쪽 번역`}>
                <TranslatedPage
                  pdfDocument={pdfDocument}
                  pageIndex={index}
                  viewport={viewport}
                  entry={translation.entries.get(index)}
                  root={mainRef}
                  onVisible={load}
                  onHover={hover}
                  linked={linked}
                  message={translation.entries.get(index)?.status === "ready" ? null : pageStatus(translation, index, pages[index]).text}
                />
              </section>
            ))
          : Array.from({ length: pageCount }, (_, index) => (
              <TextPage
                key={index}
                pageIndex={index}
                translation={translation}
                info={pages[index]}
                root={mainRef}
                onVisible={load}
                onHover={hover}
                linked={linked}
              />
            ))}
      </main>
    </div>
  );
}

/** 글로 읽기의 한 쪽: 쪽 번호와 번역문. 화면에 들어오면 저장된 번역을 읽는다. */
function TextPage({
  pageIndex,
  translation,
  info,
  root,
  onVisible,
  onHover,
  linked,
}: Readonly<{
  pageIndex: number;
  translation: Translation;
  info: PageInfo | undefined;
  root: RefObject<HTMLElement | null>;
  onVisible: (pageIndex: number) => void;
  onHover: (hover: SourceHover) => void;
  linked: LinkedSentence;
}>) {
  const ref = useRef<HTMLElement>(null);
  const visible = useInView(ref, root);
  const [fontSize] = useTranslationFont();
  useEffect(() => {
    if (visible) onVisible(pageIndex);
  }, [visible, pageIndex, onVisible]);
  return (
    <section ref={ref} className="translation-tab-page is-text" data-tab-page={pageIndex} aria-label={`${pageIndex + 1}쪽 번역`}>
      <h2 className="translation-tab-page-number">{pageIndex + 1}쪽</h2>
      <TranslationText
        pageIndex={pageIndex}
        entry={translation.entries.get(pageIndex)}
        fontSize={fontSize}
        status={pageStatus(translation, pageIndex, info).text}
        onHover={onHover}
        linked={linked}
      />
    </section>
  );
}
