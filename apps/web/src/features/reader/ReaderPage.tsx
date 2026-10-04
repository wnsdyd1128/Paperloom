import "pdfjs-dist/web/pdf_viewer.css";
import "./reader.css";

import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist";
import type { EventBus, PDFPageView, PDFViewer } from "pdfjs-dist/web/pdf_viewer.mjs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Icon, type IconName } from "../../shared/Icon";
import { type Anchor, type Annotation, createAnchor, getAnchor, type NewAnchor, type RegionKind } from "../annotations/api";
import type { HighlightColor } from "../annotations/api";
import { rememberHighlightColor, storedHighlightColor } from "../annotations/highlights";
import { HighlightsPanel } from "../annotations/HighlightsPanel";
import { NotesPanel } from "../annotations/NotesPanel";
import { useAnnotations } from "../annotations/useAnnotations";
import { useBridge } from "../chat/BridgeStatus";
import { usePreferences } from "../settings/PreferencesProvider";
import { SettingsDialog } from "../settings/SettingsDialog";
import { openTranslationChannel, pageInfos, scrollDelta, type TranslationChannel, viewPosition } from "../translation/channel";
import { ReflowPanel, TRANSLATION_GAP, TranslationBar, TranslationLayer, useTranslationView } from "../translation/ReaderTranslation";
import { type LinkedSentence, useLinkedSentence } from "../translation/linkedSentence";
import { sourceQuads } from "../translation/sourceHighlight";
import type { SourceHover } from "../translation/TranslatedPage";
import type { TranslationMode } from "../translation/TranslationControls";
import { useTranslation } from "../translation/useTranslation";
import { formatRoute } from "../../app/route";
import { ChatPanel, type ChatRequest } from "../chat/ChatPanel";
import { DEFAULT_QUESTIONS } from "../context/api";
import { type Paper, sourcePdfUrl, type Version } from "../library/api";
import { type Draft, InlineLayer, type Placed, type Spot } from "../threads/InlineLayer";
import { ThreadsPanel } from "../threads/ThreadsPanel";
import { type InlineThread, useInlineThreads } from "../threads/useInlineThreads";
import { ClipboardUnavailable, copyImageToClipboard, isCopyShortcut, isEditable, pageRegionImageUrl } from "./clipboard";
import { CLICK_SLOP_PX, useFigurePicking } from "./figures";
import { FindBar, type FindMatches } from "./FindBar";
import { boxToQuad, type Quad } from "./geometry";
import { navigationKeyAction } from "./navigationKeys";
import type { ReadingLine, TocEntry } from "./outline";
import { PageTextStatus, usePageTexts } from "./PageTextStatus";
import { PaperInfoMenu } from "./PaperInfo";
import { loadPdfJs } from "./pdfjs";
import { ReaderHeader } from "./ReaderHeader";
import { useReferenceLinks } from "./referenceLinks";
import { useSideWidth } from "./SideResizer";
import { useRegionDrawing } from "./regionDrawing";
import {
  type AnnotationMark,
  contentFrame,
  drawAnnotationOverlay,
  drawQuadOverlay,
  drawSourceOverlay,
  type PageTarget,
  quadsClientRect,
  type ReaderSelection,
  scrollQuadIntoView,
  selectionToPageQuads,
  surroundingText,
} from "./selection";
import { type MenuAction, SelectionMenu } from "./SelectionMenu";
import { estimateScriptedQuote } from "./subscripts";
import { type FocusedText, type TextFocus, useTextFocus } from "./textFocus";
import { TocPanel, useTocState } from "./TocPanel";
import { ReturnBar, useViewReturns } from "./viewReturn";
import { createZoomPinner, DEFAULT_ZOOM, normalizeZoom, stepZoom, wheelZoomFactor, zoomKeyAction } from "./zoom";

const CONTEXT_CHARS = 64; // anchor.v1 prefix·suffix 길이
const EQUATION_QUESTION = "이 수식을 LaTeX로 옮기고, 각 기호의 뜻과 수식이 말하는 바를 설명해 주세요.";
const NOTICE_MS = 4000;

/** 오른쪽 사이드바 패널 (시안 레일): Claude와 대화, 선택 설명·질문, 하이라이트(U5), 주석 */
type Panel = "chat" | "threads" | "highlights" | "notes";
const PANEL_KEY = "paperloom.reader.panel"; // 이 브라우저에서만 기억하는 편의 설정
const RAIL: readonly Readonly<{ panel: Panel; label: string; icon: IconName }>[] = [
  { panel: "chat", label: "Claude와 대화", icon: "chat" },
  { panel: "threads", label: "선택 설명·질문", icon: "sparkles" },
  { panel: "highlights", label: "하이라이트", icon: "highlighter" },
  { panel: "notes", label: "주석", icon: "notes" },
];

function storedPanel(): { panel: Panel; open: boolean } {
  const known = (value: string | null | undefined) => RAIL.find((item) => item.panel === value)?.panel;
  try {
    const value = localStorage.getItem(PANEL_KEY);
    const open = known(value);
    if (open) return { panel: open, open: true };
    if (value?.startsWith("closed:")) return { panel: known(value.slice("closed:".length)) ?? "notes", open: false };
  } catch {
    // 기억하지 못해도 기본값으로 연다
  }
  return { panel: "chat", open: true };
}

type LoadState = "loading" | "ready" | "failed";
/** 주소의 anchor: 없음, 확인 중, 이 버전의 위치, 이 버전에서 찾을 수 없음 */
type LinkedAnchor =
  | Readonly<{ kind: "none" }>
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "found"; anchor: Anchor }>
  | Readonly<{ kind: "unavailable" }>;
type Notice = Readonly<{ tone: "ok" | "error"; text: string }>;
/** 첫 답 전의 창과 그 창이 저장할 선택 */
type DraftState = Draft & Readonly<{ newAnchor: NewAnchor }>;

type Props = Readonly<{
  paper: Paper;
  /** 여는 SourceVersion. 링크가 고정한 버전이면 최신 버전이 아닐 수 있다 (IMPL §6.3). */
  version: Version;
  anchorId: string | null;
  /** 답변 화면에서 연 대화의 session_id (U6). 원문 위 대화면 그 창을, 아니면 사이드바 대화에서 연다 */
  openSession: string | null;
  /** 검색 결과에서 연 쪽·문단 (W05). 강조하고 그곳으로 스크롤한다. */
  textFocus: TextFocus | null;
  anchorHref: (anchorId: string) => string;
  /** 지금 쪽의 버전 고정 주소 (위치 링크 복사) */
  pageHref: (pageNumber: number) => string;
  /** 주소의 anchor를 바꾼다. replace면 방문 기록을 늘리지 않는다. */
  onNavigate: (anchorId: string | null, options?: { replace?: boolean }) => void;
  /** 주소의 쪽·문단(page·block)을 바꿔 그 문단을 강조한다 (보낸 근거의 "원문에서 보기"). */
  onFocusText: (pageIndex: number, blockId: string) => void;
  /** 논문 정보 창에서 고친 논문 (머리의 제목 등이 바뀐다) */
  onPaperChange: (paper: Paper) => void;
  onClose: () => void;
}>;

export function ReaderPage({ paper, version, anchorId, openSession, textFocus, anchorHref, pageHref, onNavigate, onFocusText, onPaperChange, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<PDFViewer | null>(null);
  // PDF.js 이벤트 핸들러가 최신 선택·주석 표시를 읽도록 state와 함께 ref에도 둔다.
  const selectionRef = useRef<ReaderSelection | null>(null);
  const marksRef = useRef<ReadonlyMap<number, AnnotationMark[]>>(new Map());
  // 방금 저장한 위치는 이미 화면에 있으므로 주소가 바뀌어도 스크롤하지 않는다.
  const skipScrollRef = useRef<string | null>(null);
  const [load, setLoad] = useState<LoadState>("loading");
  const [pageCount, setPageCount] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(DEFAULT_ZOOM); // PDF.js의 scalechanging을 따라간다
  const [rotation, setRotation] = useState(0);
  const [selection, setSelection] = useState<ReaderSelection | null>(null);
  const [regionKind, setRegionKind] = useState<RegionKind>("figure");
  // 영역 선택 모드 (W04a): 본문에서 끈 사각형이 그림·표·수식 영역이 된다.
  const [regionMode, setRegionMode] = useState(false);
  const [{ panel, open: panelOpen }, setPanelState] = useState(storedPanel);
  const [chatRequest, setChatRequest] = useState<ChatRequest | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // 고른 것 곁의 메뉴. 끌어서 고르는 중에는 띄우지 않고 손을 뗀 뒤 띄운다.
  const [menuOpen, setMenuOpen] = useState(false);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [asking, setAsking] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  // 원문 위 창의 자리를 다시 잴 때마다 바뀐다(확대·회전·쪽 크기·창 크기).
  const [layout, setLayout] = useState(0);
  const pointerDownRef = useRef(false);
  // 모든 쪽의 실제 크기를 안 뒤에야 링크 위치로 스크롤할 수 있다 (앞쪽 크기가 바뀌면 뒤쪽이 밀린다).
  const [pagesLoaded, setPagesLoaded] = useState(false);
  const [linked, setLinked] = useState<LinkedAnchor>({ kind: "none" });
  // Ctrl+클릭으로 따라간 참고문헌 항목. 링크로 연 위치처럼 강조하고 Esc·빈 곳 누르기로 지운다.
  const [followed, setFollowed] = useState<FocusedText | null>(null);
  // 따라가기 전에 보던 자리들 ("N쪽으로 돌아가기"·Alt+←)
  const returns = useViewReturns(containerRef);
  // 탐색 (U4): 목차 패널과 찾기 줄. 찾기는 PDF.js PDFFindController가 하고 개수는 그 사건으로 받는다.
  const [toc, setToc] = useTocState();
  const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null);
  const eventBusRef = useRef<EventBus | null>(null);
  const [find, setFind] = useState({ open: false, focusKey: 0 });
  const [findMatches, setFindMatches] = useState<FindMatches>({ current: 0, total: 0 });
  const [findPending, setFindPending] = useState(false);
  const versionId = version.version_id;
  const annotations = useAnnotations(versionId);
  const pageTexts = usePageTexts(versionId);
  const focusedText = useTextFocus(versionId, textFocus);
  const bridge = useBridge();
  const inline = useInlineThreads({ paperId: paper.paper_id, bridgeUrl: bridge.resolveUrl, onBridgeOffline: bridge.markOffline });
  const relayout = useCallback(() => requestAnimationFrame(() => setLayout((count) => count + 1)), []);
  const side = useSideWidth();
  // 쪽 번역 (U7): 켬·보기 방식은 이 브라우저에 기억한다. 별도 탭으로 보면 번역 차례는 그 탭이 맡는다.
  const [translationView, setTranslationView] = useTranslationView();
  const { preferences } = usePreferences();
  const translationPages = useMemo(() => pageInfos(pageTexts?.pages ?? []), [pageTexts]);
  const translation = useTranslation({
    versionId,
    language: preferences.answer_language,
    bridge,
    pages: translationPages,
    current: pageNumber - 1,
    active: translationView.on && translationView.mode !== "tab",
  });
  const translationChannel = useRef<TranslationChannel | null>(null);
  const translationRef = useRef(translation);
  translationRef.current = translation;
  const translationTab = useRef<Window | null>(null);
  const sourcePage = useRef<number | null>(null);

  useEffect(() => {
    if (notice?.tone !== "ok") return;
    const timer = window.setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    const container = containerRef.current!;
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    setPagesLoaded(false);
    (async () => {
      const { pdfjsLib, viewer: viewerModule } = await loadPdfJs();
      if (cancelled) return;
      const eventBus = new viewerModule.EventBus();
      // 찾기(U4)가 찾은 쪽으로 옮기는 데 링크 서비스를 쓴다. PDF의 링크 주석은 여전히 그리지 않는다.
      const linkService = new viewerModule.PDFLinkService({ eventBus });
      const findController = new viewerModule.PDFFindController({ linkService, eventBus });
      const viewer = new viewerModule.PDFViewer({
        container,
        viewer: container.querySelector<HTMLDivElement>(".pdfViewer")!,
        eventBus,
        linkService,
        findController,
        removePageBorders: true,
        annotationMode: pdfjsLib.AnnotationMode.DISABLE, // 링크·양식은 v0.1 범위 밖
      });
      linkService.setViewer(viewer);
      viewerRef.current = viewer;
      eventBusRef.current = eventBus;
      eventBus.on("updatefindmatchescount", ({ matchesCount }: { matchesCount: FindMatches }) => setFindMatches(matchesCount));
      eventBus.on("updatefindcontrolstate", ({ state, matchesCount }: { state: number; matchesCount: FindMatches }) => {
        setFindPending(state === viewerModule.FindState.PENDING);
        setFindMatches(matchesCount);
      });
      eventBus.on("pagesinit", () => {
        viewer.currentScale = DEFAULT_ZOOM;
        setPageCount(viewer.pagesCount);
        setLoad("ready");
        relayout();
        // 키보드 쪽 이동(PageDown 등)은 포커스를 가진 스크롤 영역에 작동한다. 다른 곳에 포커스가 없을 때만 옮긴다.
        if (!document.activeElement || document.activeElement === document.body) container.focus({ preventScroll: true });
      });
      eventBus.on("pagesloaded", () => {
        setPagesLoaded(true);
        relayout();
      });
      eventBus.on("pagechanging", ({ pageNumber }: { pageNumber: number }) => setPageNumber(pageNumber));
      // PDF.js는 text layer를 포커스 가능하게 만든다(tabindex=0). 본문을 클릭하면 그 층이 포커스를 받는데, 확대로
      // 다시 그리거나 캐시에서 내릴 때 층이 숨겨지면 포커스가 body로 빠져 키보드 이동이 끊긴다. 그래서 포커스는
      // 숨겨지지 않는 스크롤 영역(.reader-scroll)만 받게 한다.
      eventBus.on("textlayerrendered", ({ source }: { source: PDFPageView }) => source.textLayer?.div.removeAttribute("tabindex"));
      eventBus.on("scalechanging", ({ scale }: { scale: number }) => {
        setZoom(scale);
        // 새 배율의 viewport는 이미 정해졌다. 휠 확대 중에도 표시가 따라오도록 다시 그리기를 기다리지 않는다.
        redrawAllOverlays();
        relayout();
      });
      // 회전도 viewport가 바로 바뀌고, PDF.js가 쪽을 초기화하며 표시 층을 지운다. 다시 그리기 전에 바로 되살린다.
      eventBus.on("rotationchanging", () => {
        redrawAllOverlays();
        relayout();
      });
      // 확대·회전·가상화로 페이지를 다시 그리면 선택·주석 표시도 새 viewport 기준으로 다시 그린다.
      eventBus.on("pagerendered", ({ pageNumber }: { pageNumber: number }) => {
        redrawOverlay(pageNumber - 1);
        figurePicking.prefetch(pageNumber - 1); // 보이는 쪽의 그림 후보를 미리 받는다
      });
      loadingTask = pdfjsLib.getDocument({ url: sourcePdfUrl(versionId) });
      const pdfDocument = await loadingTask.promise;
      if (cancelled) return;
      viewer.setDocument(pdfDocument);
      linkService.setDocument(pdfDocument);
      setPdfDocument(pdfDocument);
    })().catch(() => {
      if (!cancelled) setLoad("failed");
    });
    return () => {
      cancelled = true;
      viewerRef.current = null;
      eventBusRef.current = null;
      // 불러오는 중이면 취소하고, 열린 문서는 worker 자원까지 해제한다.
      void loadingTask?.destroy();
    };
  }, [versionId]);

  // 사이드바를 여닫거나 창 크기가 바뀌면 쪽이 가로로 옮겨지므로 원문 위 창의 자리를 다시 잰다.
  useEffect(() => {
    const observer = new ResizeObserver(relayout);
    observer.observe(containerRef.current!);
    return () => observer.disconnect();
  }, [relayout]);

  useEffect(() => {
    let frame = 0;
    const onSelectionChange = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const viewer = viewerRef.current;
        const domSelection = document.getSelection();
        if (!viewer || !domSelection || domSelection.isCollapsed) return; // 비우면 마지막 선택을 유지한다
        // PDF 쪽 안의 선택만 본다. 원문 위 창의 글을 고른 것은 쪽 위에 겹쳐 있어도 PDF 선택이 아니다.
        if (!containerRef.current?.querySelector(".pdfViewer")?.contains(domSelection.anchorNode)) return;
        const targets = allPageTargets(viewer);
        const pages = selectionToPageQuads(domSelection, targets);
        if (pages.length === 0) return;
        // 한 쪽 선택만 저장할 수 있으므로 첨자 추정과 앞뒤 문맥도 그때만 만든다.
        const single = pages.length === 1 ? pages[0] : null;
        const textLayer = single && pageTarget(viewer, single.pageIndex)?.element.querySelector(".textLayer");
        const context = textLayer ? surroundingText(domSelection.getRangeAt(0), textLayer, CONTEXT_CHARS) : { prefix: "", suffix: "" };
        replaceSelection({
          kind: "text",
          text: domSelection.toString().replace(/\s+/g, " ").trim(),
          displayQuote: single ? estimateScriptedQuote(single.fragments) : null,
          ...context,
          pages,
        });
      });
    };
    document.addEventListener("selectionchange", onSelectionChange);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("selectionchange", onSelectionChange);
    };
  }, []);

  useRegionDrawing(containerRef, regionMode, {
    resolvePage: (pageIndex) => (viewerRef.current ? pageTarget(viewerRef.current, pageIndex) : null),
    onRegion: (region) => {
      document.getSelection()?.removeAllRanges();
      replaceSelection({ kind: "region", ...region });
    },
    onExit: () => setRegionMode(false),
  });

  // 일반 PDF 뷰어처럼 그림을 누르면 그 그림이 영역 선택이 된다 (종류 기본값은 그림).
  const figurePicking = useFigurePicking(containerRef, {
    versionId,
    resolvePage: (pageIndex) => (viewerRef.current ? pageTarget(viewerRef.current, pageIndex) : null),
    onPick: (pageIndex, figure) => {
      document.getSelection()?.removeAllRanges();
      replaceSelection({ kind: "region", pageIndex, quad: boxToQuad(figure.box) });
    },
  });

  const referencePages = useMemo(
    () => (pageTexts?.pages ?? []).filter((item) => item.flags.includes("references")).map((item) => item.page_index),
    [pageTexts],
  );
  useReferenceLinks(containerRef, {
    versionId,
    referencePages,
    onFollow: (target) => {
      returns.remember(); // 스크롤하기 전에
      setFollowed(target);
    },
    onMiss: (text) => setNotice({ tone: "ok", text }), // 잠시 보이고 사라지는 안내(오류처럼 남기지 않는다)
  });

  function replaceSelection(next: ReaderSelection | null) {
    selectionRef.current = next;
    setSelection(next);
    redrawAllOverlays();
    if (next?.kind === "region") setRegionKind("figure");
    if (next === null) setMenuOpen(false);
    else if (next.kind === "region" || !pointerDownRef.current) setMenuOpen(true);
  }

  // 글을 끌어서 고르는 동안에는 메뉴를 띄우지 않고, 손을 떼면 띄운다.
  useEffect(() => {
    const container = containerRef.current!;
    let pressed: { x: number; y: number; selection: ReaderSelection | null } | null = null;
    const onPointerDown = (event: PointerEvent) => {
      pointerDownRef.current = !(event.target as Element).closest(".inline-layer");
      // 쪽 영역(.pdfViewer) 안만 본다. 스크롤 막대를 누른 것은 빈 곳 누르기가 아니다.
      const inPages = (event.target as Element).closest(".pdfViewer") !== null;
      // Ctrl을 누른 채 누르기는 참고문헌 번호 따라가기(referenceLinks)라 빈 곳 누르기가 아니다.
      const plain = event.button === 0 && !event.ctrlKey && !event.metaKey;
      pressed = inPages && plain ? { x: event.clientX, y: event.clientY, selection: selectionRef.current } : null;
      // 본문에서 끄는 동안에는 원문 위 칩·창이 포인터를 가로막지 않게 한다(칩 아래 글도 고를 수 있다).
      if (pointerDownRef.current) container.classList.add("is-selecting");
    };
    const onPointerUp = (event: PointerEvent) => {
      container.classList.remove("is-selecting");
      if (!pointerDownRef.current) return;
      pointerDownRef.current = false;
      const click = event.type === "pointerup" && pressed && Math.hypot(event.clientX - pressed.x, event.clientY - pressed.y) <= CLICK_SLOP_PX ? pressed : null;
      pressed = null;
      requestAnimationFrame(() => {
        const textSelected = !(document.getSelection()?.isCollapsed ?? true);
        if (selectionRef.current?.kind === "text" && textSelected) setMenuOpen(true);
        // 본문을 끌지 않고 눌렀고 글도 그림도 새로 고르지 않았다(빈 곳): 고른 표시와 링크로 연 위치의 강조를 지운다.
        if (click && !textSelected && selectionRef.current === click.selection) dismissRef.current();
      });
    };
    container.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointerup", onPointerUp);
    // 고른 글 안에서 누르면 브라우저가 글 끌어 놓기를 시작해 pointerup 대신 pointercancel이 온다.
    window.addEventListener("pointercancel", onPointerUp);
    return () => {
      container.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
    };
  }, []);

  const closeMenu = useCallback(() => setMenuOpen(false), []);
  const selectionRect = useCallback(() => {
    const viewer = viewerRef.current;
    const spot = selectionSpot(selectionRef.current);
    const target = viewer && spot && pageTarget(viewer, spot.pageIndex);
    return target && spot ? quadsClientRect(target, spot.quads) : null;
  }, []);

  /** 원문 위 자리를 스크롤 내용 좌표로 잰다 (원문 위 창·칩). */
  const place = useCallback((spot: Spot): Placed | null => {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    const target = viewer && pageTarget(viewer, spot.pageIndex);
    const rect = target && quadsClientRect(target, spot.quads);
    if (!container || !target || !rect) return null;
    const frame = container.getBoundingClientRect();
    const page = target.element.getBoundingClientRect();
    const dx = container.scrollLeft - frame.left;
    const dy = container.scrollTop - frame.top;
    return { left: rect.left + dx, top: rect.top + dy, right: rect.right + dx, bottom: rect.bottom + dy, pageLeft: page.left + dx, pageRight: page.right + dx };
  }, []);

  function openPanel(next: Panel, open = true) {
    setPanelState({ panel: next, open });
    try {
      localStorage.setItem(PANEL_KEY, open ? next : `closed:${next}`);
    } catch {
      // 기억하지 못해도 이번 화면에서는 바뀐다
    }
  }

  /** 선택 메뉴의 동작 (docs/UI_PLAN.md U2). 설명·번역은 원문 위 창에서 바로 묻고, 질문·주석은 창을 연다. */
  async function onMenuAction(action: MenuAction, color?: HighlightColor) {
    const current = selectionRef.current;
    const newAnchor = selectionAnchor(current, versionId, regionKind);
    const spot = selectionSpot(current);
    if (!newAnchor || !spot) return;
    setNotice(null);
    setMenuOpen(false);
    if (action === "copy") {
      await copySelection();
      return;
    }
    if (action === "highlight") {
      const chosen = color ?? storedHighlightColor();
      rememberHighlightColor(chosen);
      await saveAnnotation(newAnchor, "", chosen).catch(() =>
        setNotice({ tone: "error", text: "하이라이트를 저장하지 못했습니다. 백엔드 연결을 확인하세요." }),
      );
      return;
    }
    if (action === "note" || action === "ask") {
      const quote = current?.kind === "text" ? (current.displayQuote ?? current.text) : "";
      setDraft({ kind: action, spot, quote, newAnchor });
      return;
    }
    setAsking(true);
    try {
      const anchor = await createAnchor(newAnchor);
      const equation = current?.kind === "region" && regionKind === "equation";
      const question = action === "translate" ? DEFAULT_QUESTIONS.translate : equation ? EQUATION_QUESTION : DEFAULT_QUESTIONS.explain;
      clearSelection();
      void inline.start(action, anchor, question);
    } catch {
      setNotice({ tone: "error", text: "Claude에게 보낼 문맥을 만들지 못했습니다. 백엔드 연결을 확인하세요." });
    } finally {
      setAsking(false);
    }
  }

  /** 질문 창은 보내고, 메모 창은 주석으로 저장한다. */
  async function submitDraft(text: string) {
    if (!draft) return;
    if (draft.kind === "note") {
      await saveAnnotation(draft.newAnchor, text)
        .then(() => setDraft(null))
        .catch(() => setNotice({ tone: "error", text: "주석을 저장하지 못했습니다. 백엔드 연결을 확인하세요." }));
      return;
    }
    try {
      const anchor = await createAnchor(draft.newAnchor);
      setDraft(null);
      clearSelection();
      void inline.start("ask", anchor, text);
    } catch {
      setNotice({ tone: "error", text: "Claude에게 보낼 문맥을 만들지 못했습니다. 백엔드 연결을 확인하세요." });
    }
  }

  async function draftToSidebar(text: string) {
    if (!draft) return;
    try {
      const anchor = await createAnchor(draft.newAnchor);
      setDraft(null);
      clearSelection();
      setChatRequest({ kind: "attach", anchor, text: text.trim() || undefined, nonce: Date.now() });
      openPanel("chat");
    } catch {
      setNotice({ tone: "error", text: "고른 위치를 저장하지 못했습니다. 백엔드 연결을 확인하세요." });
    }
  }

  async function moveToSidebar(key: string) {
    try {
      const thread = await inline.moveToSidebar(key);
      if (!thread) return;
      setChatRequest({ kind: "open", sessionId: thread.session_id, nonce: Date.now() });
      openPanel("chat");
    } catch {
      setNotice({ tone: "error", text: "사이드바로 옮기지 못했습니다." });
    }
  }

  function openThread(item: InlineThread) {
    if (item.thread?.placement === "sidebar") {
      setChatRequest({ kind: "open", sessionId: item.thread.session_id, nonce: Date.now() });
      openPanel("chat");
      return;
    }
    scrollToAnchor(item.anchor);
    void inline.expand(item.key);
  }

  // 답변 화면에서 연 대화 (U6): 저장된 대화 목록을 받은 뒤 한 번 연다. 원문 위 대화의 위치는 주소(anchor)가 보인다.
  const openedSession = useRef<string | null>(null);
  useEffect(() => {
    if (!openSession || !inline.loaded || openedSession.current === openSession) return;
    openedSession.current = openSession;
    const item = inline.items.find((entry) => entry.thread?.session_id === openSession);
    if (item?.thread?.placement === "inline") {
      void inline.expand(item.key);
      return;
    }
    setChatRequest({ kind: "open", sessionId: openSession, nonce: Date.now() });
    openPanel("chat");
  }, [openSession, inline.loaded, inline.items]);

  /** 선택한 그림·영역을 이미지로 클립보드에 복사한다. 영역 선택이 아니면 아무것도 하지 않는다. */
  async function copySelection() {
    const current = selectionRef.current;
    if (current?.kind !== "region") return;
    const us = current.quad.filter((_, index) => index % 2 === 0);
    const vs = current.quad.filter((_, index) => index % 2 === 1);
    const box = { u0: Math.min(...us), v0: Math.min(...vs), u1: Math.max(...us), v1: Math.max(...vs) };
    try {
      await copyImageToClipboard(pageRegionImageUrl(versionId, current.pageIndex, box));
      setNotice({ tone: "ok", text: "그림을 클립보드에 복사했습니다." });
    } catch (failure) {
      const text =
        failure instanceof ClipboardUnavailable
          ? "이 주소에서는 브라우저가 클립보드에 이미지를 쓰지 못하게 합니다. 127.0.0.1이나 localhost로 열어 주세요."
          : "그림을 복사하지 못했습니다. 브라우저의 클립보드 권한을 확인하세요.";
      setNotice({ tone: "error", text });
    }
  }

  async function copyLink() {
    const href = linked.kind === "found" ? anchorHref(linked.anchor.anchor_id) : pageHref(pageNumber);
    try {
      await navigator.clipboard.writeText(new URL(href, location.origin).href);
      setNotice({ tone: "ok", text: linked.kind === "found" ? "이 위치의 링크를 복사했습니다." : `${pageNumber}쪽 링크를 복사했습니다.` });
    } catch {
      setNotice({ tone: "error", text: "링크를 복사하지 못했습니다. 브라우저의 클립보드 권한을 확인하세요." });
    }
  }

  // 주소의 anchor를 확인한다. 다른 버전의 위치면 이 버전으로 옮기지 않고 알린다 (IMPL §6.3).
  useEffect(() => {
    if (!anchorId) {
      setLinked({ kind: "none" });
      return;
    }
    let cancelled = false;
    setLinked({ kind: "loading" });
    getAnchor(anchorId)
      .then((anchor) => {
        if (!cancelled) setLinked(anchor.version_id === versionId ? { kind: "found", anchor } : { kind: "unavailable" });
      })
      .catch(() => {
        if (!cancelled) setLinked({ kind: "unavailable" });
      });
    return () => {
      cancelled = true;
    };
  }, [anchorId, versionId]);

  // 저장된 주석과 링크로 연 위치를 쪽별 표시로 만든다.
  useEffect(() => {
    const items = annotations.state.kind === "ready" ? annotations.state.items : [];
    const focusedId = linked.kind === "found" ? linked.anchor.anchor_id : null;
    const marks = new Map<number, AnnotationMark[]>();
    const add = (anchor: Anchor, annotationId: string, color: HighlightColor | null = null) => {
      const page = marks.get(anchor.page_index) ?? [];
      page.push(...anchor.quads.map((quad) => ({ quad, annotationId, focused: anchor.anchor_id === focusedId, color })));
      marks.set(anchor.page_index, page);
    };
    items.forEach((item) => add(item.anchor, item.annotation_id, item.color));
    // 주석이 지워져도 링크의 위치(Anchor)는 남으므로 그것만으로도 보여 준다.
    if (linked.kind === "found" && !items.some((item) => item.anchor.anchor_id === focusedId)) add(linked.anchor, "");
    // 검색에서 연 문단과 따라간 참고문헌 항목도 링크 위치처럼 강조한다.
    for (const text of [focusedText, followed]) {
      if (!text) continue;
      const page = marks.get(text.pageIndex) ?? [];
      page.push(...text.quads.map((quad) => ({ quad, annotationId: "", focused: true })));
      marks.set(text.pageIndex, page);
    }
    marksRef.current = marks;
    redrawAllOverlays();
  }, [annotations.state, linked, focusedText, followed]);

  useEffect(() => {
    if (linked.kind !== "found" || !pagesLoaded) return;
    if (skipScrollRef.current === linked.anchor.anchor_id) return;
    scrollToAnchor(linked.anchor);
  }, [linked, pagesLoaded]);

  // 검색에서 연 문단과 따라간 참고문헌 항목으로 스크롤한다.
  useEffect(() => {
    if (focusedText && pagesLoaded) scrollToText(focusedText);
  }, [focusedText, pagesLoaded]);
  useEffect(() => {
    if (followed) scrollToText(followed);
  }, [followed]);

  /** 문단의 첫 줄로 스크롤한다. 문단을 찾지 못했으면(quads가 비면) 그 쪽을 연다. */
  function scrollToText(text: FocusedText) {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    const target = viewer && pageTarget(viewer, text.pageIndex);
    if (!viewer || !container || !target) return;
    if (text.quads.length > 0) scrollQuadIntoView(container, target, text.quads[0]);
    else viewer.currentPageNumber = text.pageIndex + 1;
  }

  function scrollToAnchor(anchor: Anchor) {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    const target = viewer && pageTarget(viewer, anchor.page_index);
    if (container && target) scrollQuadIntoView(container, target, anchor.quads[0]);
  }

  /** 목차 항목으로 간다. PDF 목차는 그 목적지로(배율은 그대로), 본문 제목은 그 줄로. */
  function goToEntry(entry: TocEntry) {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    if (!viewer || !container) return;
    if (entry.target.kind === "dest") {
      viewer.scrollPageIntoView({ pageNumber: entry.pageIndex + 1, destArray: [...entry.target.dest], ignoreDestinationZoom: true });
      // PDF.js는 목적지를 맨 위에 둔다. 본문 제목·링크처럼 위쪽 3분의 1에 두어 지금 항목을 고르는 읽는 줄과 맞춘다.
      container.scrollTop -= container.clientHeight / 3;
      return;
    }
    const target = pageTarget(viewer, entry.pageIndex);
    const [u0, v0, u1, v1] = entry.target.box;
    if (target) scrollQuadIntoView(container, target, boxToQuad({ u0, v0, u1, v1 }));
  }

  /** 읽는 줄: 스크롤 영역 위쪽 3분의 1(목차·링크로 간 줄이 오는 곳)이 걸친 쪽. 쪽 사이 틈이면 그 위 쪽이다 (목차의 지금 항목). */
  const readingLine = useCallback((): ReadingLine | null => {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    if (!viewer || !container || viewer.pagesCount === 0) return null;
    const line = container.getBoundingClientRect().top + container.clientHeight / 3;
    let found: ReadingLine | null = null;
    // 쪽 번호(가장 많이 보이는 쪽) 조금 앞부터 본다. 읽는 줄은 그 쪽이나 앞 쪽에 있다.
    for (let index = Math.max(0, viewer.currentPageNumber - 3); index < viewer.pagesCount; index++) {
      const target = pageTarget(viewer, index);
      if (!target) continue;
      if (target.element.getBoundingClientRect().top > line) break;
      found = {
        pageIndex: index,
        above: (entry) => (quadsClientRect(target, [boxToQuad({ u0: entry.box[0], v0: entry.box[1], u1: entry.box[2], v1: entry.box[3] })])?.top ?? 0) <= line + 2,
      };
    }
    return found;
  }, []);

  /** 번역문에 마우스를 올린 동안 원문 쪽에 그 원문 문장을 강조한다(U7). 별도 탭의 강조도 이것으로 그린다. null이면 지운다. */
  const showSource = useCallback((hover: SourceHover) => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const previous = sourcePage.current !== null ? pageTarget(viewer, sourcePage.current) : null;
    if (previous) drawSourceOverlay(previous, []);
    sourcePage.current = null;
    const target = hover && pageTarget(viewer, hover.pageIndex);
    if (!hover || !target) return;
    drawSourceOverlay(target, sourceQuads(target, hover));
    sourcePage.current = hover.pageIndex;
  }, []);

  // 원문 문장 → 번역 문장 강조(2026-10-04 사용자 요청: 반대 방향). 그 원문 문장도 같은 표시로 강조한다. 번역문 위에서 그린
  // 원문 강조(번역 → 원문)를 원문 쪽을 벗어날 때 지우지 않도록, 원문 위에서 그린 강조인지 기억한다.
  const [linkedSentence, setLinkedSentence] = useState<LinkedSentence>(null);
  const linkedSource = useRef(false);
  const showSourceFromTranslation = useCallback(
    (hover: SourceHover) => {
      linkedSource.current = false;
      showSource(hover);
    },
    [showSource],
  );
  useLinkedSentence(containerRef, {
    enabled: translationView.on,
    resolvePage: (index) => (viewerRef.current ? pageTarget(viewerRef.current, index) : null),
    entry: (index) => translation.entries.get(index),
    load: (index) => void translation.load(index),
    onChange: (next, hover) => {
      if (hover) {
        linkedSource.current = true;
        showSource(hover);
      } else if (linkedSource.current) {
        linkedSource.current = false;
        showSource(null);
      }
      if (translationView.mode === "tab") translationChannel.current?.post({ type: "linked", linked: next });
      else setLinkedSentence(next);
    },
  });

  /** 레이아웃 유지: 원문 쪽과 번역 쪽이 함께 들어가지 않으면 배율을 줄인다(시안). */
  function fitForTranslation() {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    const view = viewer?.getPageView(pageNumber - 1);
    if (!viewer || !container || !view?.viewport) return;
    const room = container.clientWidth - TRANSLATION_GAP - 48;
    if (view.viewport.width * 2 > room) applyZoom((viewer.currentScale * room) / (view.viewport.width * 2));
  }

  function openTranslationTab() {
    const url = formatRoute({ kind: "translation", paperId: paper.paper_id, versionId, page: pageNumber });
    translationTab.current = window.open(url, `paperloom-translation-${versionId}`);
  }

  function chooseTranslationMode(mode: TranslationMode) {
    setTranslationView({ on: true, mode });
    showSource(null);
    if (mode === "tab") openTranslationTab();
    if (mode === "layout") requestAnimationFrame(fitForTranslation);
  }

  function toggleTranslation() {
    if (translationView.on) {
      setTranslationView({ ...translationView, on: false });
      showSource(null);
      return;
    }
    chooseTranslationMode(translationView.mode);
  }

  // 별도 탭과 쪽 이동을 맞추고, 그 탭의 문장 강조를 그린다.
  const translationTabOpen = translationView.on && translationView.mode === "tab";
  const pageNumberRef = useRef(pageNumber);
  pageNumberRef.current = pageNumber;
  const goToPageRef = useRef<(number: number) => void>(() => undefined);
  goToPageRef.current = goToPage;
  // 별도 탭이 옮긴 쪽은 그 탭에 되돌려 보내지 않는다(그 탭을 스크롤하는 동안 늦게 닿은 앞 쪽으로 되돌아가지 않게)
  const remotePageRef = useRef<number | null>(null);
  // 레이아웃 유지 번역 탭과는 쪽 안 자리까지 맞춘다. 그 탭이 보낸 자리로 옮긴 scrollTop(되돌려 보내지 않는다)
  const remoteScrollRef = useRef<number | null>(null);
  useEffect(() => {
    const container = containerRef.current;
    if (!translationTabOpen || !container) return;
    const pageDivs = () => Array.from(container.querySelectorAll<HTMLElement>(".pdfViewer .page"));
    const postScroll = () =>
      channel.post({ type: "scroll", ...viewPosition(container.getBoundingClientRect().top, pageDivs().map(contentFrame)) });
    const channel = openTranslationChannel(versionId, (message) => {
      if (message.type === "hello") {
        channel.post({ type: "page", pageIndex: pageNumberRef.current - 1 });
        postScroll();
      }
      if (message.type === "page" && message.pageIndex !== pageNumberRef.current - 1) {
        remotePageRef.current = message.pageIndex;
        goToPageRef.current(message.pageIndex + 1);
      }
      if (message.type === "scroll") {
        const div = pageDivs()[message.pageIndex];
        if (!div) return;
        container.scrollTop += scrollDelta(container.getBoundingClientRect().top, contentFrame(div), message.offset);
        remoteScrollRef.current = container.scrollTop;
      }
      if (message.type === "hover") showSourceFromTranslation(message.hover);
      if (message.type === "translated") translationRef.current.reload(message.pageIndex);
    });
    const onScroll = () => {
      if (remoteScrollRef.current !== null && Math.abs(container.scrollTop - remoteScrollRef.current) < 2) return;
      remoteScrollRef.current = null;
      postScroll();
    };
    container.addEventListener("scroll", onScroll, { passive: true });
    translationChannel.current = channel;
    return () => {
      container.removeEventListener("scroll", onScroll);
      channel.close();
      translationChannel.current = null;
      showSource(null);
    };
  }, [translationTabOpen, versionId, showSource, showSourceFromTranslation]);
  useEffect(() => {
    const remote = remotePageRef.current;
    remotePageRef.current = null;
    if (remote !== pageNumber - 1) translationChannel.current?.post({ type: "page", pageIndex: pageNumber - 1 });
  }, [pageNumber]);

  /** 찾기 줄을 열고 입력칸에 포커스한다(열려 있으면 글을 고른다). */
  function openFind() {
    setFind((value) => ({ open: true, focusKey: value.focusKey + 1 }));
  }

  function findText(query: string, { again, previous }: Readonly<{ again: boolean; previous: boolean }>) {
    eventBusRef.current?.dispatch("find", {
      source: null,
      type: again ? "again" : "",
      query,
      caseSensitive: false,
      entireWord: false,
      highlightAll: true,
      findPrevious: previous,
      matchDiacritics: false,
    });
  }

  /** 찾기 줄을 닫고 강조를 지운 뒤 본문으로 포커스를 돌린다. */
  function closeFind() {
    eventBusRef.current?.dispatch("findbarclose", { source: null });
    setFind((value) => ({ ...value, open: false }));
    setFindMatches({ current: 0, total: 0 });
    containerRef.current?.focus({ preventScroll: true });
  }

  function goToPage(number: number) {
    const viewer = viewerRef.current;
    if (viewer && number >= 1 && number <= viewer.pagesCount) viewer.currentPageNumber = number;
  }

  function redrawOverlay(pageIndex: number) {
    const viewer = viewerRef.current;
    const target = viewer && pageTarget(viewer, pageIndex);
    if (!target) return;
    drawQuadOverlay(target, selectionQuads(selectionRef.current, pageIndex));
    drawAnnotationOverlay(target, marksRef.current.get(pageIndex) ?? []);
  }

  function redrawAllOverlays() {
    const count = viewerRef.current?.pagesCount ?? 0;
    for (let pageIndex = 0; pageIndex < count; pageIndex++) redrawOverlay(pageIndex);
  }

  /** 선택을 주석으로 저장한다. 주소에 위치를 남겨 새로고침해도 같은 위치로 돌아온다. */
  async function saveAnnotation(anchor: NewAnchor, comment: string, color: HighlightColor | null = null) {
    const saved = await annotations.create(anchor, comment, color);
    clearSelection();
    setNotice({ tone: "ok", text: color ? "하이라이트를 저장했습니다." : "주석을 저장했습니다." });
    skipScrollRef.current = saved.anchor.anchor_id;
    onNavigate(saved.anchor.anchor_id, { replace: true });
  }

  function clearSelection() {
    document.getSelection()?.removeAllRanges();
    replaceSelection(null);
    setRegionMode(false);
  }

  /**
   * Esc나 본문 빈 곳 누르기 (2026-10-02 사용자 확인: Ctrl로 고른 영역·근거에서 연 위치의 강조를 끌 방법이 없었다).
   * 고른 글·영역의 표시와 메뉴, 따라간 참고문헌 항목의 강조를 지우고, 주소의 위치(anchor)·문단(page·block)을 빼 그 강조를 지운다. 저장한 주석은
   * 그대로 보인다. 영역 모드는 그대로 둔다(Esc는 regionDrawing이 끈다).
   */
  function dismiss() {
    document.getSelection()?.removeAllRanges();
    if (selectionRef.current) replaceSelection(null);
    setFollowed(null);
    if (anchorId || textFocus) onNavigate(null, { replace: true });
  }
  const dismissRef = useRef(dismiss);
  useEffect(() => {
    dismissRef.current = dismiss;
  });

  /** 참고문헌으로 가기 전에 보던 자리로 돌아가고 따라간 항목의 강조를 지운다. 돌아갈 곳이 없었으면 false */
  function goBack(): boolean {
    if (!returns.back()) return false;
    setFollowed(null);
    return true;
  }
  const goBackRef = useRef(goBack);
  useEffect(() => {
    goBackRef.current = goBack;
  });

  function showAnchor(target: string) {
    skipScrollRef.current = null;
    // 이미 주소에 있는 위치면 주소는 그대로이므로 여기서 직접 스크롤한다.
    if (target === anchorId && linked.kind === "found" && pagesLoaded) scrollToAnchor(linked.anchor);
    else onNavigate(target);
  }

  async function removeAnnotation(annotation: Annotation) {
    await annotations.remove(annotation);
    // 주소의 anchor는 주석이 없어도 강조된다(지운 주석을 가리키는 옛 링크도 그 위치를 연다). 방금 지운 주석의
    // 위치가 주소에 있으면 강조가 남으므로 주소에서 위치를 뺀다.
    if (annotation.anchor.anchor_id === anchorId) onNavigate(null, { replace: true });
  }

  function openAnnotation(annotation: Annotation) {
    skipScrollRef.current = null;
    // 이미 주소에 있는 위치를 다시 누르면 주소는 그대로이므로 여기서 직접 스크롤한다.
    if (annotation.anchor.anchor_id === anchorId && pagesLoaded) scrollToAnchor(annotation.anchor);
    else onNavigate(annotation.anchor.anchor_id);
  }

  useEffect(() => {
    const container = containerRef.current!;
    // Ctrl+휠은 본문 위에서만 가로챈다(머리·패널 위에서는 브라우저 자체 확대). React의 onWheel은 passive로
    // 등록되어 기본 동작을 막을 수 없으므로 직접 등록한다. 트랙패드 핀치도 ctrlKey가 켜진 휠 이벤트로 온다.
    const pinner = createZoomPinner(container);
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const restorePin = pinner.pin(event.clientX, event.clientY); // 커서 아래 PDF 지점을 제자리에 둔다
      applyZoom(currentScale() * wheelZoomFactor(event.deltaY, event.deltaMode));
      restorePin();
    };
    // 확대 단축키는 Reader가 열려 있는 동안 포커스 위치와 무관하게 받는다. 키에는 위치가 없고 Reader가 화면 전체다.
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.isComposing && !isEditable(document.activeElement)) {
        dismissRef.current();
        return;
      }
      // Alt+←: 참고문헌에서 보던 자리로 돌아간다. 돌아갈 곳이 없으면 브라우저의 뒤로 가기로 둔다.
      const altLeft = event.key === "ArrowLeft" && event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey;
      if (altLeft && !isEditable(document.activeElement) && goBackRef.current()) {
        event.preventDefault();
        return;
      }
      // 그림·영역이 선택돼 있으면 Ctrl+C는 그 이미지를 복사한다. 텍스트를 선택했거나 글 쓰는 칸에 있으면
      // 브라우저의 텍스트 복사를 그대로 둔다.
      if (isCopyShortcut(event)) {
        const textSelected = !(document.getSelection()?.isCollapsed ?? true);
        if (selectionRef.current?.kind !== "region" || textSelected || isEditable(document.activeElement)) return;
        event.preventDefault();
        void copySelection();
        return;
      }
      // 목차(Ctrl+Shift+O)와 본문 찾기(Ctrl+F, 브라우저 찾기 대신)도 Reader가 열려 있는 동안 받는다.
      const navigation = navigationKeyAction(event);
      if (navigation) {
        event.preventDefault();
        if (navigation === "toc") setToc((value) => ({ ...value, open: !value.open }));
        else openFind();
        return;
      }
      const action = zoomKeyAction(event);
      if (!action) return;
      event.preventDefault(); // 브라우저 자체 확대 대신 PDF 배율을 바꾼다
      if (action === "reset") applyZoom(DEFAULT_ZOOM);
      else zoomStep(action === "in" ? 1 : -1);
    };
    container.addEventListener("wheel", onWheel, { passive: false });
    document.addEventListener("keydown", onKeyDown);
    return () => {
      container.removeEventListener("wheel", onWheel);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  function currentScale(): number {
    return viewerRef.current?.currentScale ?? DEFAULT_ZOOM;
  }

  function applyZoom(scale: number) {
    const viewer = viewerRef.current;
    // 페이지 크기를 바로 바꾸고 scalechanging을 보낸다. 스크롤은 보이던 영역의 왼쪽 위를 유지한다.
    if (viewer) viewer.currentScale = normalizeZoom(scale);
  }

  // 머리 단추와 Ctrl+±가 같은 함수를 써서 결과가 같다.
  function zoomStep(direction: 1 | -1) {
    applyZoom(stepZoom(currentScale(), direction));
  }

  function rotateClockwise() {
    const next = (rotation + 90) % 360;
    if (viewerRef.current) viewerRef.current.pagesRotation = next;
    setRotation(next);
  }

  const ready = load === "ready";
  const pinnedOlderVersion = versionId !== paper.current_version.version_id;
  const showCitation = (citation: { block_id: string | null; page_index: number; anchor_id: string }) =>
    citation.block_id ? onFocusText(citation.page_index, citation.block_id) : showAnchor(citation.anchor_id);
  // 원문 위 대화(사이드바로 옮기지 않은 것)와 원문 위 창에서 지운 대화는 사이드바 "Claude와 대화" 기록에 두지 않는다
  const hiddenSessions = useMemo(
    () =>
      new Set([
        ...inline.items.filter((item) => item.thread && item.thread.placement !== "sidebar").map((item) => item.thread!.session_id),
        ...inline.removed,
      ]),
    [inline.items, inline.removed],
  );
  const counts: Readonly<Record<Panel, number>> = {
    chat: 0,
    threads: inline.items.length,
    highlights: annotations.state.kind === "ready" ? annotations.state.items.filter((item) => item.color).length : 0,
    notes: annotations.state.kind === "ready" ? annotations.state.items.length : 0,
  };
  const togglePanel = (next: Panel) => openPanel(next, !(panelOpen && panel === next));
  // 메모가 있는 주석은 본문 옆 칩으로도 보인다(2026-10-02 사용자 요청). 하이라이트만 한 주석은 표시만 있다.
  const annotationItems = annotations.state.kind === "ready" ? annotations.state.items : [];
  const noteSpots = annotationItems
    .filter((item) => item.comment.trim())
    .map((item) => ({
      id: item.annotation_id,
      spot: { pageIndex: item.anchor.page_index, quads: item.anchor.quads },
      text: item.comment.trim(),
      quote: item.anchor.display_quote ?? item.anchor.quote,
    }));
  const annotationById = (id: string) => annotationItems.find((item) => item.annotation_id === id);
  return (
    <div className="reader">
      <ReaderHeader
        title={paper.title}
        ready={ready}
        pageNumber={pageNumber}
        pageCount={pageCount}
        zoom={zoom}
        rotation={rotation}
        regionMode={regionMode}
        bridge={bridge}
        pageStatus={ready && <PageTextStatus texts={pageTexts} pageIndex={pageNumber - 1} />}
        onHome={onClose}
        onOpenSettings={() => setSettingsOpen(true)}
        onGoToPage={goToPage}
        onZoom={applyZoom}
        onZoomStep={zoomStep}
        onRotate={rotateClockwise}
        onToggleRegion={() => setRegionMode((active) => !active)}
        translationOn={translationView.on}
        onToggleTranslation={toggleTranslation}
        onOpenChat={() => openPanel("chat")}
        onSummary={() => {
          setChatRequest({ kind: "summary", nonce: Date.now() });
          openPanel("chat");
        }}
        onCopyLink={() => void copyLink()}
        tocOpen={toc.open}
        findOpen={find.open}
        info={<PaperInfoMenu paper={paper} version={version} texts={pageTexts} onSaved={onPaperChange} />}
        onToggleToc={() => setToc((value) => ({ ...value, open: !value.open }))}
        onOpenFind={openFind}
      />
      <div className="reader-notices">
        {load === "loading" && (
          <p className="status pending reader-notice" role="status">
            PDF를 불러오는 중…
          </p>
        )}
        {load === "failed" && (
          <p className="status error reader-notice" role="status">
            PDF를 열 수 없습니다.
          </p>
        )}
        {pinnedOlderVersion && (
          <p className="status pending reader-notice" role="status" data-testid="pinned-version-notice">
            링크에 고정된 이전 버전({new Date(version.created_at).toLocaleString("ko-KR")} 등록)을 보고 있습니다. 최신 버전으로 바꾸지
            않았습니다.
          </p>
        )}
        {linked.kind === "unavailable" && (
          <p className="status error reader-notice" role="status">
            링크의 원문 위치를 이 버전에서 찾을 수 없습니다.
          </p>
        )}
        {translationView.on && ready && (
          <TranslationBar
            translation={translation}
            language={preferences.answer_language}
            mode={translationView.mode}
            pageIndex={pageNumber - 1}
            pageCount={pageCount}
            info={translationPages[pageNumber - 1]}
            onMode={chooseTranslationMode}
            onClose={toggleTranslation}
            onFocusTab={() => (translationTab.current && !translationTab.current.closed ? translationTab.current.focus() : openTranslationTab())}
          />
        )}
      </div>
      {/* 방금 한 일의 안내는 본문을 밀지 않도록 위에 띄운다. 성공 안내는 잠시 뒤 사라진다. */}
      {notice && (
        <p className={`status ${notice.tone} reader-toast`} role="status">
          {notice.text}
        </p>
      )}
      <SelectionStatus selection={selection} />
      {menuOpen && selection && (
        <SelectionMenu
          kind={selection.kind}
          blockedReason={selection.kind === "text" && selection.pages.length > 1 ? "한 쪽 안에서 고르세요" : null}
          regionKind={regionKind}
          onRegionKind={setRegionKind}
          getRect={selectionRect}
          scrollContainer={containerRef.current}
          busy={asking}
          onAction={(action, color) => void onMenuAction(action, color)}
          onClose={closeMenu}
        />
      )}
      <div className="reader-body">
        {toc.open && (
          <TocPanel
            pdfDocument={pdfDocument}
            versionId={versionId}
            textReady={pageTexts !== null && pageTexts.status !== "READY_TO_READ" && pageTexts.status !== "PARSING"}
            pageCount={pageCount}
            pageIndex={pageNumber - 1}
            rotation={rotation}
            mode={toc.mode}
            onMode={(mode) => setToc((value) => ({ ...value, mode }))}
            onGoToPage={goToPage}
            onGoToEntry={goToEntry}
            scrollRef={containerRef}
            readingLine={readingLine}
          />
        )}
        <main className={translationView.on && translationView.mode === "reflow" ? "reader-stage is-reflow" : "reader-stage"}>
          {/*
            PDFViewer는 절대 위치 컨테이너와 그 안의 .pdfViewer를 요구한다. 원문 위 창(.inline-layer)은 같은 스크롤
            영역에 두어 원문과 함께 움직인다.

            lang="und": PDF 본문은 UI 언어(ko)를 물려받으면 안 된다. PDF.js text layer는 PDF의 /Lang(없으면 "")을
            준 canvas로 글자 폭을 재고, span은 DOM의 lang으로 sans-serif 등을 고른다. lang="ko"를 물려받으면
            다른 글꼴이 골라져 선택 영역이 실제 글자보다 최대 10% 좁아진다. Edge에서 canvas lang=""와 같은
            글꼴을 고르는 DOM 값은 "und"였다. PDFViewer가 .pdfViewer의 lang을 직접 관리(초기화 때 제거,
            PDF에 /Lang이 있으면 설정)하므로 그 바깥 컨테이너에 둔다.
          */}
          <div
            ref={containerRef}
            className={["reader-scroll", regionMode && "region-mode", translationView.on && translationView.mode === "layout" && "is-translating"].filter(Boolean).join(" ")}
            tabIndex={0}
            aria-label="PDF 본문"
            lang="und"
          >
            <div className="pdfViewer" />
            <div lang="ko">
              <InlineLayer
                paperId={paper.paper_id}
                threads={inline}
                notes={noteSpots}
                onShowNote={(id) => {
                  const annotation = annotationById(id);
                  if (!annotation) return;
                  openPanel("notes");
                  openAnnotation(annotation);
                }}
                onSaveNote={async (id, text) => {
                  const annotation = annotationById(id);
                  if (annotation) await annotations.update(annotation, text);
                }}
                onRemoveNote={async (id) => {
                  const annotation = annotationById(id);
                  if (annotation) await removeAnnotation(annotation);
                }}
                draft={draft}
                place={place}
                layout={layout}
                onSendDraft={submitDraft}
                onCloseDraft={() => setDraft(null)}
                onDraftToSidebar={(text) => void draftToSidebar(text)}
                onMoveToSidebar={(key) => void moveToSidebar(key)}
                onSaveTranslation={async (item, text) => {
                  await annotations.attach(item.anchor.anchor_id, text);
                  setNotice({ tone: "ok", text: "주석을 저장했습니다." });
                }}
                onShowCitation={showCitation}
                onShowAnchor={showAnchor}
                onShowBlock={onFocusText}
                onShowPage={goToPage}
              />
            </div>
            {translationView.on && translationView.mode === "layout" && pdfDocument && (
              <div lang="ko">
                <TranslationLayer
                  viewer={viewerRef.current}
                  pdfDocument={pdfDocument}
                  scrollRef={containerRef}
                  layoutKey={`${layout}:${pageCount}`}
                  translation={translation}
                  pages={translationPages}
                  onHover={showSourceFromTranslation}
                  linked={linkedSentence}
                />
              </div>
            )}
          </div>
          {translationView.on && translationView.mode === "reflow" && (
            <ReflowPanel
              translation={translation}
              pageIndex={pageNumber - 1}
              pageCount={pageCount}
              info={translationPages[pageNumber - 1]}
              onClose={toggleTranslation}
              onHover={showSourceFromTranslation}
              linked={linkedSentence}
            />
          )}
          <ReturnBar spots={returns.spots} onBack={goBack} onClose={returns.clear} />
          {find.open && <FindBar focusKey={find.focusKey} matches={findMatches} pending={findPending} onFind={findText} onClose={closeFind} />}
        </main>
        {/* 사이드바를 바꾸거나 닫아도 대화·입력이 남도록 패널을 숨기기만 한다. */}
        <aside className="reader-side" hidden={!panelOpen} aria-label="사이드바" style={{ width: side.width }}>
          {side.handle}
          <div className="side-panel side-chat" hidden={panel !== "chat"}>
            <ChatPanel
              paperId={paper.paper_id}
              versionId={versionId}
              pageIndex={pageNumber - 1}
              bridge={bridge}
              request={chatRequest}
              visible={panelOpen && panel === "chat"}
              hiddenSessions={hiddenSessions}
              onShowCitation={showCitation}
              onShowAnchor={showAnchor}
              onShowPage={goToPage}
              onDiscarded={inline.answerDiscarded}
              onSessionRenamed={inline.sessionRenamed}
              onSessionDeleted={inline.sessionDeleted}
            />
          </div>
          <div className="side-panel" hidden={panel !== "threads"}>
            <ThreadsPanel items={inline.items} active={inline.expanded} onOpen={openThread} />
          </div>
          <div className="side-panel" hidden={panel !== "highlights"}>
            <HighlightsPanel
              state={annotations.state}
              focusedAnchorId={linked.kind === "found" ? linked.anchor.anchor_id : null}
              anchorHref={anchorHref}
              onOpen={openAnnotation}
              onRecolor={annotations.recolor}
              onRemove={removeAnnotation}
            />
          </div>
          <div className="side-panel" hidden={panel !== "notes"}>
            <NotesPanel
              state={annotations.state}
              focusedAnchorId={linked.kind === "found" ? linked.anchor.anchor_id : null}
              anchorHref={anchorHref}
              onOpen={openAnnotation}
              onUpdate={annotations.update}
              onChangeKind={annotations.changeKind}
              onRemove={removeAnnotation}
            />
          </div>
        </aside>
        <nav className="reader-rail" aria-label="사이드바 패널">
          <button
            type="button"
            className="rail-button"
            aria-label={panelOpen ? "사이드바 닫기" : "사이드바 열기"}
            aria-expanded={panelOpen}
            title="사이드바 열기/닫기"
            onClick={() => openPanel(panel, !panelOpen)}
          >
            <Icon name="panel" size={18} />
          </button>
          <span className="rail-rule" aria-hidden="true" />
          {RAIL.map((item) => (
            <button
              key={item.panel}
              type="button"
              className="rail-button rail-item"
              aria-label={item.label}
              aria-pressed={panelOpen && panel === item.panel}
              title={`${item.label} (다시 누르면 닫기)`}
              onClick={() => togglePanel(item.panel)}
            >
              <Icon name={item.icon} size={18} />
              {counts[item.panel] > 0 && (
                <span className="rail-badge" aria-hidden="true">
                  {counts[item.panel]}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>
      {settingsOpen && <SettingsDialog bridge={bridge} onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}

/**
 * 지금 고른 것을 화면 낭독기에 알린다(화면에는 보이지 않는다). 메뉴가 뜨기 전 무엇을 골랐는지, 여러 쪽에 걸쳐
 * 저장할 수 없는지, 첨자를 추정한 표기가 무엇인지 알 수 있다.
 */
function SelectionStatus({ selection }: { selection: ReaderSelection | null }) {
  let text = "";
  if (selection?.kind === "text") {
    text =
      selection.pages.length > 1
        ? "여러 쪽에 걸친 선택은 주석으로 저장할 수 없습니다. 쪽마다 따로 선택하세요."
        : `${selection.pages[0].pageIndex + 1}쪽에서 ${selection.pages[0].quads.length}줄을 골랐습니다: ${selection.text}` +
          (selection.displayQuote ? ` (추정 표기: ${selection.displayQuote})` : "");
  } else if (selection?.kind === "region") {
    text = `${selection.pageIndex + 1}쪽에서 영역을 골랐습니다.`;
  }
  const single = selection?.kind === "text" && selection.pages.length === 1 ? selection : null;
  return (
    <p className="sr-only" role="status" data-testid="selection-status" data-quote={single?.text} data-display-quote={single?.displayQuote ?? undefined}>
      {text}
    </p>
  );
}

/** 지금 선택을 저장할 Anchor 요청. 저장할 수 없으면(선택 없음, 여러 쪽 선택) null. */
function selectionAnchor(current: ReaderSelection | null, versionId: string, regionKind: RegionKind): NewAnchor | null {
  if (current?.kind === "text" && current.pages.length === 1) {
    const [page] = current.pages;
    return {
      schema_version: "anchor.v1",
      kind: "text",
      version_id: versionId,
      page_index: page.pageIndex,
      quads: page.quads,
      quote: current.text,
      display_quote: current.displayQuote,
      prefix: current.prefix,
      suffix: current.suffix,
    };
  }
  if (current?.kind === "region") {
    // 영역은 사각형 하나다. 인용·첨자 추정·앞뒤 문맥은 없다 (IMPL §10.6).
    return {
      schema_version: "anchor.v1",
      kind: regionKind,
      version_id: versionId,
      page_index: current.pageIndex,
      quads: [current.quad],
      quote: "",
      display_quote: null,
      prefix: "",
      suffix: "",
    };
  }
  return null;
}

/** 지금 선택의 원문 위 자리(첫 쪽) */
function selectionSpot(current: ReaderSelection | null): Spot | null {
  if (current?.kind === "region") return { pageIndex: current.pageIndex, quads: [current.quad] };
  return current?.kind === "text" ? { pageIndex: current.pages[0].pageIndex, quads: current.pages[0].quads } : null;
}

/** 현재 선택에서 한 쪽에 그릴 quad들 */
function selectionQuads(selection: ReaderSelection | null, pageIndex: number): readonly Quad[] {
  if (selection?.kind === "region") return selection.pageIndex === pageIndex ? [selection.quad] : [];
  return selection?.pages.find((page) => page.pageIndex === pageIndex)?.quads ?? [];
}

function pageTarget(viewer: PDFViewer, pageIndex: number): PageTarget | null {
  const pageView = viewer.getPageView(pageIndex);
  return pageView?.div && pageView.viewport ? { pageIndex, element: pageView.div, viewport: pageView.viewport } : null;
}

function allPageTargets(viewer: PDFViewer): PageTarget[] {
  return Array.from({ length: viewer.pagesCount }, (_, index) => pageTarget(viewer, index)).filter((target): target is PageTarget => target !== null);
}
