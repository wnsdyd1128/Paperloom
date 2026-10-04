/**
 * 서재의 태그 메뉴 (U6, 시안 Library): 줄마다 태그 붙이기(+), 표 머리의 태그 거르기 메뉴.
 * 거르기 메뉴에서 태그 이름을 바꾸거나 지운다(모든 논문, 2026-10-04 사용자 요청). 바깥을 누르거나 Esc로 닫는다.
 */
import { type RefObject, useEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";
import type { TagFilter, TagMode } from "./tagFilter";

function useDismiss(open: boolean, close: () => void, ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.isComposing) close();
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close, ref]);
}

type EditorProps = Readonly<{
  title: string;
  tags: readonly string[];
  /** 서재의 모든 태그 이름 */
  known: readonly string[];
  onChange: (tags: readonly string[]) => void;
}>;

/**
 * 줄의 "+": 있는 태그를 켜고 끄거나 새 태그를 적는다. 바꿀 때마다 저장한다. 창이 열려 있는 동안에는 연 때의 목록을 그대로 두어,
 * 마지막으로 쓰던 태그를 끄더라도 그 줄이 사라지지 않는다(다시 켤 수 있다).
 */
export function TagEditor({ title, tags, known, onChange }: EditorProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [listed, setListed] = useState<readonly string[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(open, () => setOpen(false), ref);
  const has = (name: string) => tags.some((tag) => tag.toLowerCase() === name.toLowerCase());
  const union = (first: readonly string[], second: readonly string[]) => [
    ...first,
    ...second.filter((name) => !first.some((item) => item.toLowerCase() === name.toLowerCase())),
  ];
  const names = union(union(listed, known), tags);

  function add() {
    const name = draft.trim();
    setDraft("");
    if (name && !has(name)) onChange([...tags, name]);
  }

  return (
    <div className="tag-editor" ref={ref}>
      <button type="button" className="tag-add" aria-label={`${title} 태그 붙이기`} title="태그 붙이기" aria-expanded={open}
        onClick={() => {
          if (!open) setListed(union(known, tags));
          setOpen(!open);
        }}
      >
        +
      </button>
      {open && (
        <div className="tag-popover" role="dialog" aria-label="태그 붙이기">
          <input
            className="input"
            aria-label="새 태그"
            placeholder="새 태그 이름 (Enter)"
            maxLength={40}
            value={draft}
            autoFocus
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                event.preventDefault();
                add();
              }
            }}
          />
          {names.map((name) => (
            <label key={name} className="tag-check">
              <input
                type="checkbox"
                checked={has(name)}
                onChange={() => onChange(has(name) ? tags.filter((tag) => tag.toLowerCase() !== name.toLowerCase()) : [...tags, name])}
              />
              {name}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

type FilterProps = Readonly<{
  filter: TagFilter;
  counts: readonly Readonly<{ name: string; count: number }>[];
  untaggedCount: number;
  onChange: (filter: TagFilter) => void;
  /** 태그 이름 바꾸기(모든 논문) */
  onRename: (name: string, next: string) => void;
  /** 태그 지우기(모든 논문) */
  onDelete: (name: string) => void;
}>;

/** 표 머리 "태그": 태그를 골라 거른다(하나라도/모두 포함), 또는 태그 없는 논문만. */
export function TagFilterMenu({ filter, counts, untaggedCount, onChange, onRename, onDelete }: FilterProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null); // 이름을 고치는 태그
  const ref = useRef<HTMLDivElement>(null);
  // 닫으면 찾기 글을 지운다. 다시 열었을 때 남은 글이 태그를 숨기지 않게.
  const close = () => {
    setOpen(false);
    setQuery("");
  };
  useDismiss(open, close, ref);
  const active = filter.untagged || filter.tags.length > 0;
  const needle = query.trim().toLowerCase();
  const chosen = (name: string) => filter.tags.some((tag) => tag.toLowerCase() === name.toLowerCase());
  const toggle = (name: string) =>
    onChange({ ...filter, untagged: false, tags: chosen(name) ? filter.tags.filter((tag) => tag.toLowerCase() !== name.toLowerCase()) : [...filter.tags, name] });
  const setMode = (mode: TagMode) => onChange({ ...filter, mode });

  return (
    <div className="tag-filter" ref={ref}>
      <button type="button" className={active ? "tag-filter-button is-active" : "tag-filter-button"} aria-haspopup="dialog" aria-expanded={open} onClick={() => (open ? close() : setOpen(true))}>
        태그
        <Icon name="filter" size={12} />
      </button>
      {open && (
        <div className="tag-popover tag-filter-popover" role="dialog" aria-label="태그로 거르기">
          <input className="input" aria-label="태그 찾기" placeholder="태그 찾기" value={query} onChange={(event) => setQuery(event.target.value)} />
          {counts
            .filter((item) => !needle || item.name.toLowerCase().includes(needle))
            .map((item) =>
              renaming === item.name ? (
                <TagRename
                  key={item.name}
                  name={item.name}
                  onDone={(next) => {
                    setRenaming(null);
                    if (next && next !== item.name) onRename(item.name, next);
                  }}
                />
              ) : (
                <div key={item.name} className="tag-row">
                  <label className="tag-check">
                    <input type="checkbox" checked={chosen(item.name)} onChange={() => toggle(item.name)} />
                    <span className="tag-check-name">{item.name}</span>
                    <span className="muted">{item.count}</span>
                  </label>
                  <button type="button" className="btn btn-icon tag-tool" aria-label={`${item.name} 태그 이름 바꾸기`} title="이름 바꾸기" onClick={() => setRenaming(item.name)}>
                    <Icon name="pencil" size={12} />
                  </button>
                  <button
                    type="button"
                    className="btn btn-icon tag-tool"
                    aria-label={`${item.name} 태그 지우기`}
                    title="모든 논문에서 지우기"
                    onClick={() => window.confirm(`"${item.name}" 태그를 모든 논문에서 지울까요? 논문은 그대로입니다.`) && onDelete(item.name)}
                  >
                    <Icon name="trash" size={12} />
                  </button>
                </div>
              ),
            )}
          <label className="tag-check is-untagged">
            <input type="checkbox" checked={filter.untagged} onChange={() => onChange({ ...filter, tags: [], untagged: !filter.untagged })} />
            <span className="tag-check-name">태그 없음</span>
            <span className="muted">{untaggedCount}</span>
          </label>
          <div className="tag-filter-mode">
            <span className="muted">여러 개 고르면</span>
            <div className="seg" role="radiogroup" aria-label="여러 태그 고르기">
              <label className="seg-opt">
                <input type="radio" name="tag-mode" checked={filter.mode === "any"} onChange={() => setMode("any")} />
                하나라도
              </label>
              <label className="seg-opt">
                <input type="radio" name="tag-mode" checked={filter.mode === "all"} onChange={() => setMode("all")} />
                모두
              </label>
            </div>
          </div>
          <div className="tag-filter-foot">
            <button type="button" className="btn btn-ghost" onClick={() => onChange({ ...filter, tags: [], untagged: false })}>
              지우기
            </button>
            <button type="button" className="btn btn-plain" onClick={close}>
              닫기
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** 태그 이름 고치기 칸: Enter나 다른 곳을 누르면 바꾸고(빈 이름은 그대로), Esc는 그만둔다(메뉴는 닫지 않는다). */
function TagRename({ name, onDone }: Readonly<{ name: string; onDone: (next: string | null) => void }>) {
  const finished = useRef(false);
  const finish = (next: string | null) => {
    if (finished.current) return;
    finished.current = true;
    onDone(next?.trim() || null);
  };
  return (
    <div className="tag-row">
      <input
        className="input tag-rename"
        aria-label={`${name} 새 이름`}
        defaultValue={name}
        maxLength={40}
        autoFocus
        onFocus={(event) => event.currentTarget.select()}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing) return;
          if (event.key === "Enter") finish(event.currentTarget.value);
          if (event.key === "Escape") {
            event.stopPropagation(); // 메뉴를 닫지 않는다
            finish(null);
          }
        }}
        onBlur={(event) => finish(event.currentTarget.value)}
      />
    </div>
  );
}
