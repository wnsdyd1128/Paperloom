/**
 * 왼쪽 목차 패널 232px (U4, 시안 Reader v3 "논문 목차", IMPL §10.8). 머리의 목차 단추나 Ctrl+Shift+O로 열고 닫는다.
 * - 목차: PDF 목차(outline)를 쓰고, 없으면 본문 제목(서버, 2026-10-02 사용자 결정 D6)으로 만든다. 지금 쪽까지 나온
 *   마지막 항목을 강조한다.
 * - 쪽 미리보기: 쪽마다 작은 그림. 목록에서 보이는(가까운) 쪽만 그린다.
 * 열림·보기 방식은 이 브라우저에 기억한다(처음은 닫힘, 목차).
 */
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { type RefObject, useEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";
import { getHeadings } from "../library/api";
import { currentEntry, flattenOutline, headingEntries, pdfResolver, type ReadingLine, type TocEntry } from "./outline";

export type TocMode = "outline" | "thumbs";
type TocState = Readonly<{ open: boolean; mode: TocMode }>;

const TOC_KEY = "paperloom.reader.toc";
const THUMB_WIDTH = 150;

function storedToc(): TocState {
  try {
    const [open, mode] = (localStorage.getItem(TOC_KEY) ?? "").split(":");
    return { open: open === "open", mode: mode === "thumbs" ? "thumbs" : "outline" };
  } catch {
    return { open: false, mode: "outline" }; // 기억하지 못해도 닫힌 채로 연다
  }
}

/** 목차 패널의 열림·보기 방식. 바뀌면 기억한다. */
export function useTocState() {
  const [state, setState] = useState<TocState>(storedToc);
  useEffect(() => {
    try {
      localStorage.setItem(TOC_KEY, `${state.open ? "open" : "closed"}:${state.mode}`);
    } catch {
      // 기억하지 못해도 이번 화면에서는 바뀐다
    }
  }, [state]);
  return [state, setState] as const;
}

type Props = Readonly<{
  pdfDocument: PDFDocumentProxy | null;
  versionId: string;
  /** 본문 추출이 끝났는지(본문 제목을 받을 수 있는지) */
  textReady: boolean;
  pageCount: number;
  /** 지금 쪽(0부터) */
  pageIndex: number;
  rotation: number;
  mode: TocMode;
  onMode: (mode: TocMode) => void;
  onGoToPage: (pageNumber: number) => void;
  onGoToEntry: (entry: TocEntry) => void;
  /** Reader의 스크롤 영역. 스크롤할 때마다 지금 항목을 다시 고른다 */
  scrollRef: RefObject<HTMLElement | null>;
  readingLine: () => ReadingLine | null;
}>;

export function TocPanel(props: Props) {
  const { mode, onMode } = props;
  return (
    <aside className="toc-panel" aria-label="논문 목차">
      <div className="toc-head">
        <span className="toc-title">논문 목차</span>
        <div className="seg" role="radiogroup" aria-label="목차 보기">
          <label className="seg-opt" title="쪽 미리보기">
            <input type="radio" name="toc-mode" aria-label="쪽 미리보기" checked={mode === "thumbs"} onChange={() => onMode("thumbs")} />
            <Icon name="grid" size={14} />
          </label>
          <label className="seg-opt" title="목차">
            <input type="radio" name="toc-mode" aria-label="목차" checked={mode === "outline"} onChange={() => onMode("outline")} />
            <Icon name="list" size={14} />
          </label>
        </div>
      </div>
      {mode === "outline" ? <Outline {...props} /> : <Thumbnails {...props} />}
    </aside>
  );
}

type Source =
  | Readonly<{ kind: "loading" | "pending" | "none" }>
  | Readonly<{ kind: "pdf" | "headings"; entries: readonly TocEntry[] }>;

/** PDF 목차, 없으면 본문 제목. 본문 추출 전이면 pending(추출이 끝나면 다시 본다). */
function useTocSource(pdfDocument: PDFDocumentProxy | null, versionId: string, textReady: boolean): Source {
  const [source, setSource] = useState<Source>({ kind: "loading" });
  useEffect(() => {
    if (!pdfDocument) return;
    let cancelled = false;
    (async (): Promise<Source> => {
      const outline = await flattenOutline(await pdfDocument.getOutline(), pdfResolver(pdfDocument));
      if (outline.length > 0) return { kind: "pdf", entries: outline };
      if (!textReady) return { kind: "pending" };
      const headings = headingEntries(await getHeadings(versionId));
      return headings.length > 0 ? { kind: "headings", entries: headings } : { kind: "none" };
    })()
      .catch((): Source => ({ kind: "none" }))
      .then((next) => {
        if (!cancelled) setSource(next);
      });
    return () => {
      cancelled = true;
    };
  }, [pdfDocument, versionId, textReady]);
  return source;
}

function Outline({ pdfDocument, versionId, textReady, pageIndex, onGoToEntry, scrollRef, readingLine }: Props) {
  const source = useTocSource(pdfDocument, versionId, textReady);
  const listRef = useRef<HTMLOListElement>(null);
  const entries = source.kind === "pdf" || source.kind === "headings" ? source.entries : [];
  const [current, setCurrent] = useState(-1);
  // 누른 항목은 그 자리에서 스크롤하기 전까지 지금 항목이다. 문서 끝 쪽 제목은 읽는 줄까지 올라오지 못할 수 있어서다.
  const pinned = useRef<Readonly<{ index: number; scrollTop: number }> | null>(null);

  // 지금 항목: 읽는 줄 위의 마지막 항목(같은 쪽의 여러 제목 가운데서도). 스크롤할 때마다(한 프레임에 한 번) 다시 고른다.
  useEffect(() => {
    const container = scrollRef.current;
    const choose = () => {
      if (pinned.current && container && Math.abs(container.scrollTop - pinned.current.scrollTop) <= 2) {
        setCurrent(pinned.current.index);
        return;
      }
      pinned.current = null;
      const line = readingLine();
      setCurrent(line ? currentEntry(entries, line.pageIndex, line.above) : currentEntry(entries, pageIndex));
    };
    let frame = requestAnimationFrame(choose);
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(choose);
    };
    container?.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      container?.removeEventListener("scroll", onScroll);
    };
  }, [entries, pageIndex, scrollRef, readingLine]);

  function go(entry: TocEntry, index: number) {
    onGoToEntry(entry);
    const container = scrollRef.current;
    if (container) pinned.current = { index, scrollTop: container.scrollTop };
    setCurrent(index);
  }

  useEffect(() => {
    listRef.current?.querySelector('[aria-current="location"]')?.scrollIntoView({ block: "nearest" });
  }, [current]);

  if (source.kind === "loading") return <p className="toc-message">목차를 읽는 중…</p>;
  if (source.kind === "pending") return <p className="toc-message">PDF에 목차가 없습니다. 본문 추출이 끝나면 본문 제목으로 목차를 만듭니다.</p>;
  if (source.kind === "none") return <p className="toc-message">PDF에 목차가 없고 본문 제목도 찾지 못했습니다. 쪽 미리보기를 쓰세요.</p>;
  return (
    <>
      <ol className="toc-outline" ref={listRef}>
        {entries.map((entry, index) => (
          <li key={index}>
            <button
              type="button"
              className="toc-entry"
              data-level={entry.level}
              style={{ paddingLeft: 12 + 16 * (Math.min(entry.level, 4) - 1) }}
              aria-current={index === current ? "location" : undefined}
              title={entry.title}
              onClick={() => go(entry, index)}
            >
              <span className="toc-entry-title">{entry.title}</span>
              <span className="toc-entry-page">{entry.pageIndex + 1}</span>
            </button>
          </li>
        ))}
      </ol>
      <p className="toc-foot">{source.kind === "pdf" ? "PDF 목차(outline)에서 읽음" : "PDF에 목차가 없어 본문 제목에서 찾음"}</p>
    </>
  );
}

function Thumbnails({ pdfDocument, pageCount, pageIndex, rotation, onGoToPage }: Props) {
  const listRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    listRef.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest" });
  }, [pageIndex]);
  return (
    <ol className="toc-thumbs" ref={listRef}>
      {Array.from({ length: pageCount }, (_, index) => (
        <li key={index}>
          <Thumbnail pdfDocument={pdfDocument} index={index} current={index === pageIndex} rotation={rotation} root={listRef} onGo={() => onGoToPage(index + 1)} />
        </li>
      ))}
    </ol>
  );
}

type ThumbnailProps = Readonly<{
  pdfDocument: PDFDocumentProxy | null;
  index: number;
  current: boolean;
  rotation: number;
  root: RefObject<HTMLOListElement | null>;
  onGo: () => void;
}>;

/** 목록에서 보이기 시작하면(앞뒤 여유 포함) 한 번 그린다. 보기 회전이 바뀌면 다시 그린다. */
function Thumbnail({ pdfDocument, index, current, rotation, root, onGo }: ThumbnailProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [near, setNear] = useState(false);
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { root: root.current, rootMargin: "200px 0px" },
    );
    observer.observe(buttonRef.current!);
    return () => observer.disconnect();
  }, [root]);

  useEffect(() => {
    if (!near || !pdfDocument) return;
    let cancelled = false;
    let task: RenderTask | null = null;
    pdfDocument
      .getPage(index + 1)
      .then((page) => {
        if (cancelled) return;
        const turned = (page.rotate + rotation) % 360;
        const base = page.getViewport({ scale: 1, rotation: turned });
        const ratio = window.devicePixelRatio || 1;
        const viewport = page.getViewport({ scale: (THUMB_WIDTH * ratio) / base.width, rotation: turned });
        const canvas = canvasRef.current!;
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        canvas.style.height = `${(THUMB_WIDTH * base.height) / base.width}px`;
        task = page.render({ canvas, viewport });
        return task.promise.then(() => {
          if (!cancelled) setDrawn(true);
        });
      })
      .catch(() => undefined); // 그리지 못한 쪽은 빈 칸으로 남는다
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [near, pdfDocument, index, rotation]);

  return (
    <button
      ref={buttonRef}
      type="button"
      className="toc-thumb"
      aria-current={current ? "page" : undefined}
      aria-label={`${index + 1}쪽`}
      data-drawn={drawn}
      onClick={onGo}
    >
      <canvas ref={canvasRef} width={0} height={0} />
      <span className="toc-thumb-number">{index + 1}</span>
    </button>
  );
}
