/**
 * 레이아웃 유지 번역 쪽 (U7, 시안 Reader v3 "원문과 나란히 · 레이아웃 유지"): 원문 쪽 그림 위에 문단 상자마다 그 자리에
 * 번역문을 맞춰 넣는다. 그림·표는 원문 그대로다(그림 안 글자는 번역하지 않는다). 번역문은 원문 글꼴 크기·줄 간격·굵게·기울임을
 * 따르고(2026-10-03 사용자 요청), 문장(묶음)마다 나뉘어 마우스를 올리면 그 문장과 원문 문장을 함께 강조한다(onHover).
 * 쪽 그림은 화면에 들어올 때만 그린다.
 */
import type { PDFDocumentProxy, PageViewport, RenderTask } from "pdfjs-dist";
import { type CSSProperties, type RefObject, useEffect, useLayoutEffect, useRef, useState } from "react";

import type { TextBlock } from "../library/api";
import { boxToQuad, quadToCssRect } from "../reader/geometry";
import type { LinkedSentence } from "./linkedSentence";
import { useLayoutScale } from "./TranslationControls";
import { StyledText } from "./TranslationText";
import { type SentenceGroup, sentenceGroups } from "./sentences";
import { blockFrame, singleLineRoom, wholeMark } from "./typeset";
import type { PageEntry } from "./useTranslation";

/**
 * 원문 문장 강조: 그 쪽·문단(글과 줄 상자)과 문단 text 안 범위들. null이면 지운다. 문단을 함께 실어, 별도 탭의 강조를
 * 원문 탭이 번역을 읽지 않고도 그린다.
 */
export type SourceHover = Readonly<{ pageIndex: number; block: Pick<TextBlock, "block_id" | "text" | "regions">; ranges: SentenceGroup["ranges"] }> | null;

const MIN_FONT = 4; // px

/** 요소가 스크롤 영역(root, 없으면 문서 창)의 앞뒤 400px 안에 들어왔는지 */
export function useInView(ref: RefObject<HTMLElement | null>, root: RefObject<HTMLElement | null>): boolean {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const observer = new IntersectionObserver(([item]) => setVisible(item.isIntersecting), { root: root.current, rootMargin: "400px 0px" });
    observer.observe(ref.current!);
    return () => observer.disconnect();
  }, [ref, root]);
  return visible;
}

type Props = Readonly<{
  pdfDocument: PDFDocumentProxy;
  pageIndex: number;
  /** 원문 쪽의 viewport (CSS px, 배율·회전) */
  viewport: PageViewport;
  /** 원문 쪽 상자의 실제 크기(PDF.js가 화면 픽셀 단위로 내린 크기). 있으면 쪽 내용을 이 크기에 맞춰 늘이고 줄인다(원문 쪽과 같게) */
  size?: PageSize;
  entry: PageEntry | undefined;
  /** 쪽 그림을 그리기 시작할 범위의 스크롤 영역(없으면 문서 창) */
  root: RefObject<HTMLElement | null>;
  onVisible: (pageIndex: number) => void;
  onHover: (hover: SourceHover) => void;
  /** 원문 문장에 마우스를 올린 동안 강조할 번역 문장(다른 쪽이면 무시) */
  linked?: LinkedSentence;
  /** 쪽 위에 보일 안내(번역 전·번역 중·실패) */
  message: string | null;
}>;

export type PageSize = Readonly<{ width: number; height: number }>;

export function TranslatedPage({ pdfDocument, pageIndex, viewport, size, entry, root, onVisible, onHover, linked, message }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const visible = useInView(ref, root);
  const [scale] = useLayoutScale();

  useEffect(() => {
    if (visible) onVisible(pageIndex);
  }, [visible, pageIndex, onVisible]);

  // 원문 쪽 그림(이 배율·회전, 화면 밀도에 맞춰)
  useEffect(() => {
    if (!visible) return;
    let task: RenderTask | null = null;
    let cancelled = false;
    void pdfDocument.getPage(pageIndex + 1).then((page) => {
      if (cancelled) return;
      const ratio = window.devicePixelRatio || 1;
      const scaled = page.getViewport({ scale: viewport.scale * ratio, rotation: viewport.rotation });
      const canvas = canvasRef.current!;
      canvas.width = Math.round(scaled.width);
      canvas.height = Math.round(scaled.height);
      task = page.render({ canvas, viewport: scaled });
      task.promise.catch(() => undefined); // 다시 그리면 앞 그리기는 취소된다
    });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [visible, pdfDocument, pageIndex, viewport.scale, viewport.rotation]);

  const ready = entry?.status === "ready" ? entry : null;
  const blocks = ready ? new Map(ready.blocks.map((block) => [block.block_id, block])) : null;
  const translated = ready && blocks ? ready.translation.blocks.flatMap((item) => (blocks.has(item.block_id) ? [{ item, block: blocks.get(item.block_id)! }] : [])) : [];
  return (
    <div ref={ref} className="translated-page" data-page-index={pageIndex} style={{ width: size?.width ?? viewport.width, height: size?.height ?? viewport.height }}>
      <div
        className="translated-page-content"
        style={{
          width: viewport.width,
          height: viewport.height,
          transform: size ? `scale(${size.width / viewport.width}, ${size.height / viewport.height})` : undefined,
        }}
      >
        <canvas ref={canvasRef} className="translated-page-canvas" aria-hidden="true" />
        {/* 원문 글을 가리는 흰 바탕은 번역문 아래 층에 따로 둔다: 문단 상자가 겹쳐도(큰 첫 글자 등) 뒤 문단 바탕이 앞 문단 번역을 가리지 않는다 */}
        <div className="translated-masks" aria-hidden="true">
          {translated.map(({ block }) => {
            const frame = blockFrame(blockLines(block, viewport), block.font_size, viewport.scale, scale);
            return <div key={block.block_id} className="translated-mask" style={{ left: frame.left, top: frame.top, width: frame.width, height: frame.height }} />;
          })}
        </div>
        {translated.map(({ item, block }) => (
          <TranslatedBlockBox
            key={item.block_id}
            block={block}
            groups={sentenceGroups(item.sentences)}
            viewport={viewport}
            scale={scale}
            linkedGroup={linked?.pageIndex === pageIndex && linked.blockId === block.block_id ? linked.group : null}
            onHover={(ranges) => onHover(ranges && { pageIndex, block: { block_id: block.block_id, text: block.text, regions: block.regions }, ranges })}
          />
        ))}
      </div>
      {message && <p className="translated-page-message">{message}</p>}
    </div>
  );
}

/** 문단 줄 상자(CSS px) */
function blockLines(block: TextBlock, viewport: PageViewport) {
  return block.regions.map((region) => quadToCssRect(viewport, boxToQuad({ u0: region[0], v0: region[1], u1: region[2], v1: region[3] })));
}

function TranslatedBlockBox({
  block,
  groups,
  viewport,
  scale,
  linkedGroup,
  onHover,
}: Readonly<{
  block: TextBlock;
  groups: readonly SentenceGroup[];
  viewport: PageViewport;
  scale: number;
  linkedGroup: number | null;
  onHover: (ranges: SentenceGroup["ranges"] | null) => void;
}>) {
  const ref = useRef<HTMLDivElement>(null);
  const frame = blockFrame(blockLines(block, viewport), block.font_size, viewport.scale, scale);
  const text = groups.map((group) => group.text).join(" ");

  // 원문 크기(× 배율)에서 시작해 상자에 넘치면 넘치지 않을 때까지 글꼴만 줄인다. 글꼴은 React 밖에서 바꾼다(다시 그려도 그대로).
  useLayoutEffect(() => {
    const element = ref.current!;
    let size = frame.fontSize;
    element.style.fontSize = `${size}px`;
    const overflows = () => element.scrollWidth > element.clientWidth + 1 || (!frame.single && element.scrollHeight > element.clientHeight + 1);
    while (size > MIN_FONT && overflows()) {
      size = Math.max(MIN_FONT, size * 0.95);
      element.style.fontSize = `${size}px`;
    }
  }, [frame.fontSize, frame.single, frame.width, frame.height, text]);

  // 한 줄 문단(제목 등)은 번역이 원문보다 길면 그 단 안에서 늘려 한 줄로 둔다(상자 폭에 맞추면 글자가 너무 작아진다).
  const room = singleLineRoom(frame, viewport.width);
  const style: CSSProperties = frame.single
    ? { left: frame.left, top: frame.top, minWidth: frame.width, width: "max-content", maxWidth: room, height: frame.height, lineHeight: frame.lineHeight }
    : { left: frame.left, top: frame.top, width: frame.width, height: frame.height, lineHeight: frame.lineHeight };
  const mark = wholeMark(block);
  const className = ["translated-block", frame.single && "is-single", mark.includes("b") && "is-bold", mark.includes("i") && "is-italic"].filter(Boolean).join(" ");
  return (
    <div ref={ref} className={className} style={style} data-block-id={block.block_id}>
      {groups.map((group, index) => (
        <span
          key={index}
          className={index === linkedGroup ? "translated-sentence is-linked" : "translated-sentence"}
          onMouseEnter={() => onHover(group.ranges)}
          onMouseLeave={() => onHover(null)}
        >
          <StyledText text={group.text} />{" "}
        </span>
      ))}
    </div>
  );
}
