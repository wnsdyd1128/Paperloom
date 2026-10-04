/**
 * 글로 읽기 (U7, 시안 "원문과 나란히 · 글로 읽기"): 한 쪽의 번역문만 문단으로 이어 큰 글자로 보인다. 문장(묶음)에 마우스를
 * 올리면 그 문장과 원문 문장을 함께 강조한다(2026-10-03 사용자 요청). 원문의 굵게·기울임을 따른다.
 */
import { Fragment, type ReactNode } from "react";

import type { LinkedSentence } from "./linkedSentence";
import { type SourceHover } from "./TranslatedPage";
import { sentenceGroups } from "./sentences";
import { styledRuns, wholeMark } from "./typeset";
import type { PageEntry } from "./useTranslation";

/** 번역문(<b>·<i>·<sub>·<sup> 표시)을 굵게·기울임·아래·위첨자로 그린다. 표시 밖은 모두 글 그대로다(HTML로 읽지 않는다). */
export function StyledText({ text }: Readonly<{ text: string }>) {
  return styledRuns(text).map((run, index) => {
    let node: ReactNode = run.text;
    if (run.script === "sub") node = <sub>{node}</sub>;
    if (run.script === "sup") node = <sup>{node}</sup>;
    if (run.italic) node = <i>{node}</i>;
    if (run.bold) node = <b>{node}</b>;
    return <Fragment key={index}>{node}</Fragment>;
  });
}

type Props = Readonly<{
  pageIndex: number;
  entry: PageEntry | undefined;
  fontSize: number;
  /** 번역이 없을 때 보일 글 */
  status: string;
  onHover: (hover: SourceHover) => void;
  /** 원문 문장에 마우스를 올린 동안 강조할 번역 문장(다른 쪽이면 무시) */
  linked?: LinkedSentence;
}>;

export function TranslationText({ pageIndex, entry, fontSize, status, onHover, linked }: Props) {
  if (entry?.status !== "ready") return <p className="translation-text-status muted">{status}</p>;
  return (
    <div className="translation-text" style={{ fontSize }} lang={entry.translation.language} data-page-index={pageIndex}>
      {entry.translation.blocks.map((block) => {
        const source = entry.blocks.find((item) => item.block_id === block.block_id);
        const mark = source ? wholeMark(source) : "";
        const className = ["translation-paragraph", mark.includes("b") && "is-bold", mark.includes("i") && "is-italic"].filter(Boolean).join(" ");
        return (
          <p key={block.block_id} className={className} data-block-id={block.block_id}>
            {sentenceGroups(block.sentences).map((group, index) => (
              <span
                key={index}
                className={linked?.pageIndex === pageIndex && linked.blockId === block.block_id && linked.group === index ? "translated-sentence is-linked" : "translated-sentence"}
                onMouseEnter={() => source && onHover({ pageIndex, block: { block_id: source.block_id, text: source.text, regions: source.regions }, ranges: group.ranges })}
                onMouseLeave={() => onHover(null)}
              >
                <StyledText text={group.text} />{" "}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
