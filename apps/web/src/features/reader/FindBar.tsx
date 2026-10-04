/**
 * 본문 찾기 줄 (U4, IMPL §10.8): Ctrl+F나 머리의 찾기 단추로 본문 오른쪽 위에 연다. 찾기는 PDF.js PDFFindController가
 * 하고(대소문자 무시, 낱말 일부도 찾음, 모두 강조), 여기서는 찾는 말과 이동만 보낸다. 시안에는 단추만 있어 모양은 가정이다.
 * Enter 다음, Shift+Enter 이전, Esc 닫기(강조를 지우고 본문으로 포커스).
 */
import { useEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";

export type FindMatches = Readonly<{ current: number; total: number }>;

/** 찾는 말 옆의 개수 글. 찾는 말이 없으면 빈 글 */
export function findLabel(query: string, matches: FindMatches, pending: boolean): string {
  if (!query.trim()) return "";
  if (matches.total === 0) return pending ? "찾는 중…" : "없음";
  return `${matches.current || "–"} / ${matches.total}`;
}

type Props = Readonly<{
  /** 바뀔 때마다 입력칸에 포커스하고 글을 고른다(Ctrl+F를 다시 눌렀을 때) */
  focusKey: number;
  matches: FindMatches;
  pending: boolean;
  /** again이면 같은 말의 다음(previous면 이전) 일치로 간다 */
  onFind: (query: string, options: Readonly<{ again: boolean; previous: boolean }>) => void;
  onClose: () => void;
}>;

export function FindBar({ focusKey, matches, pending, onFind, onClose }: Props) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [focusKey]);

  const step = (previous: boolean) => {
    if (query.trim()) onFind(query, { again: true, previous });
  };
  return (
    <div className="find-bar" role="search" aria-label="본문에서 찾기">
      <input
        ref={inputRef}
        className="input find-input"
        value={query}
        placeholder="본문에서 찾기"
        aria-label="찾을 말"
        onChange={(event) => {
          setQuery(event.target.value);
          onFind(event.target.value, { again: false, previous: false });
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.nativeEvent.isComposing) {
            event.preventDefault();
            step(event.shiftKey);
          } else if (event.key === "Escape") {
            event.preventDefault();
            onClose();
          }
        }}
      />
      <span className="find-count" aria-live="polite">
        {findLabel(query, matches, pending)}
      </span>
      <button type="button" className="btn btn-icon" aria-label="이전 찾기" title="이전 (Shift+Enter)" disabled={!query.trim()} onClick={() => step(true)}>
        <Icon name="chevronUp" size={15} />
      </button>
      <button type="button" className="btn btn-icon" aria-label="다음 찾기" title="다음 (Enter)" disabled={!query.trim()} onClick={() => step(false)}>
        <Icon name="chevronDown" size={15} />
      </button>
      <button type="button" className="btn btn-icon" aria-label="찾기 닫기" title="닫기 (Esc)" onClick={onClose}>
        <Icon name="x" size={15} />
      </button>
    </div>
  );
}
