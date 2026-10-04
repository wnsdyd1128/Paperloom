import { type CSSProperties, type FormEvent, type KeyboardEvent, type PointerEvent, useEffect, useRef, useState } from "react";

import { Icon, type IconName } from "../../shared/Icon";
import { formatMathForCopy } from "../../shared/mathCopy";
import type { Quad } from "../reader/geometry";
import { AnswerMarkdown } from "../answers/AnswerMarkdown";
import { findCitation } from "../answers/citations";
import type { Citation } from "../answers/api";
import { usePreferences } from "../settings/PreferencesProvider";
import type { ThreadKind } from "./api";
import { dragOffset, type Offset } from "./drag";
import { EvidenceSummary } from "./EvidenceList";
import { type MarginChip, MarginChips } from "./MarginChips";
import { answerCount, type InlineThread, type InlineThreads } from "./useInlineThreads";

/** 원문 위 자리: 쪽과 그 쪽의 정규화 quad들 */
export type Spot = Readonly<{ pageIndex: number; quads: readonly Quad[] }>;
/** 스크롤 내용 좌표(px)로 잰 자리. 고른 것의 상자와 그 쪽의 왼쪽·오른쪽 끝 */
export type Placed = Readonly<{ left: number; top: number; right: number; bottom: number; pageLeft: number; pageRight: number }>;

/** 첫 답 전의 창: 질문 입력(ask), 메모(note) */
export type Draft = Readonly<{ kind: "ask" | "note"; spot: Spot; quote: string }>;
/** 메모가 있는 주석 (본문 옆 칩으로 보이고, 누르면 그 자리에서 펼친다). quote는 고른 글(영역이면 빈 글) */
export type NoteSpot = Readonly<{ id: string; spot: Spot; text: string; quote: string }>;

const KIND_ICONS: Readonly<Record<ThreadKind, IconName>> = { explain: "sparkles", translate: "languages", ask: "ask" };
const WINDOW_WIDTH = 520;
const WINDOW_INSET = 52; // 시안: 쪽 왼쪽 끝에서 창까지
const DRAG_GRIP = 120; // 오른쪽 끝으로 끌어도 머리가 이만큼은 보인다
const NOTE_WIDTH = 420;
const NO_OFFSET: Offset = { x: 0, y: 0 };
const TRANSLATION_FONT = { min: 12, max: 24 }; // 번역 창 글꼴 범위 (preferences/models.py의 translation_font_size)

type Props = Readonly<{
  /** 칩의 옮긴 자리를 논문마다 기억한다 */
  paperId: string;
  threads: InlineThreads;
  /** 메모가 있는 주석. 칩을 누르면 그 자리에서 펼친다 */
  notes: readonly NoteSpot[];
  /** 펼친 주석에서: 주석 패널에서 보기, 메모 고치기(비우면 본문 표시만 남는다), 지우기 */
  onShowNote: (id: string) => void;
  onSaveNote: (id: string, text: string) => Promise<void>;
  onRemoveNote: (id: string) => Promise<void>;
  draft: Draft | null;
  /** 자리를 스크롤 내용 좌표로 잰다. 그 쪽이 아직 없으면 null */
  place: (spot: Spot) => Placed | null;
  /** 확대·회전·쪽 크기가 바뀔 때마다 바뀐다(다시 잰다) */
  layout: number;
  onSendDraft: (text: string) => Promise<void>;
  onCloseDraft: () => void;
  /** 질문 창을 보내기 전에 사이드바 대화로 옮긴다(고른 위치를 입력칸에 붙인다) */
  onDraftToSidebar: (text: string) => void;
  onMoveToSidebar: (key: string) => void;
  onSaveTranslation: (item: InlineThread, text: string) => Promise<void>;
  onShowCitation: (citation: Citation) => void;
  onShowAnchor: (anchorId: string) => void;
  onShowBlock: (pageIndex: number, blockId: string) => void;
  onShowPage: (pageNumber: number) => void;
}>;

/**
 * PDF 스크롤 영역 안에서 원문과 함께 움직이는 창들 (시안 3g·3h·3i·3j). 펼친 대화 하나는 고른 자리 아래 창으로,
 * 나머지는 쪽 오른쪽의 제목 칩으로 보인다. 창 안을 눌러도 PDF 선택·영역 그리기가 시작되지 않는다(.inline-layer).
 * 펼친 창은 머리를 끌어 옮길 수 있다. 옮긴 만큼은 그 창이 펼쳐져 있고 배율이 그대로인 동안만 기억한다
 * (접었다 펴거나 확대·회전하면 고른 자리 아래로 돌아온다).
 */
export function InlineLayer({ paperId, threads, notes, onShowNote, onSaveNote, onRemoveNote, draft, place, layout, ...handlers }: Props) {
  // layout이 바뀌면 다시 그려 자리를 다시 잰다.
  const [moved, setMoved] = useState<{ key: string; layout: number; offset: Offset } | null>(null);
  // 펼친 주석. 한 번에 창 하나만 펼친다: 대화를 펼치면 주석을 접고, 주석을 펼치면 대화를 접는다.
  const [openNoteId, setOpenNoteId] = useState<string | null>(null);
  useEffect(() => {
    if (threads.expanded) setOpenNoteId(null);
  }, [threads.expanded]);
  useEffect(() => setMoved(null), [threads.expanded, openNoteId]);
  const openNote = notes.find((note) => note.id === openNoteId);
  const inline = threads.items.filter((item) => item.thread?.placement !== "sidebar");
  // 본문 옆 칩: 접은 대화와 메모가 있는 주석. 옮긴 자리는 새로고침해도 같은 키(대화 ID·주석 ID)로 기억한다.
  const chips: MarginChip[] = [
    ...inline
      .filter((item) => item.key !== threads.expanded)
      .map((item) => ({
        id: `thread:${item.thread?.session_id ?? item.key}`,
        icon: KIND_ICONS[item.kind],
        title: item.title,
        meta: `답변 ${answerCount(item)}`,
        hint: "다시 펼치기",
        spot: { pageIndex: item.anchor.page_index, quads: item.anchor.quads },
        className: "thread-chip",
        data: { "thread-key": item.key },
        onOpen: () => void threads.expand(item.key),
      })),
    ...notes
      .filter((note) => note.id !== openNoteId)
      .map((note) => ({
        id: `note:${note.id}`,
        icon: "note" as const,
        title: note.text,
        hint: "펼치기",
        spot: note.spot,
        className: "thread-chip is-note",
        data: { "note-id": note.id },
        onOpen: () => {
          threads.collapse();
          setOpenNoteId(note.id);
        },
      })),
  ];
  const open = inline.find((item) => item.key === threads.expanded);
  const openPlaced = open && place({ pageIndex: open.anchor.page_index, quads: open.anchor.quads });
  const openBase = openPlaced && windowStyle(openPlaced);
  const openOffset = open && moved?.key === open.key && moved.layout === layout ? moved.offset : NO_OFFSET;
  const draftPlaced = draft && place(draft.spot);
  const notePlaced = openNote && place(openNote.spot);
  const noteBase = notePlaced && windowStyle(notePlaced, NOTE_WIDTH);
  const noteKey = openNote ? `note:${openNote.id}` : "";
  const noteOffset = openNote && moved?.key === noteKey && moved.layout === layout ? moved.offset : NO_OFFSET;

  /** 머리를 눌러 끌기 시작한다. 머리의 버튼을 누른 것은 끌기가 아니다. */
  function grab(event: PointerEvent<HTMLElement>, key: string, base: { left: number; top: number }, start: Offset) {
    if (event.button !== 0 || (event.target as Element).closest("button")) return;
    event.preventDefault();
    const head = event.currentTarget;
    // 스크롤 내용 전체가 아니라 쪽들의 폭으로 막는다. 창이 넓힌 스크롤 폭을 따라 끌 때마다 더 밀려 나가지 않게.
    const viewer = head.closest(".reader-scroll")?.querySelector<HTMLElement>(".pdfViewer");
    const bounds = { width: viewer ? viewer.offsetLeft + viewer.scrollWidth : Infinity, grip: DRAG_GRIP };
    const origin = { x: event.clientX, y: event.clientY };
    head.setPointerCapture(event.pointerId);
    const move = (next: globalThis.PointerEvent) =>
      setMoved({ key, layout, offset: dragOffset(base, start, { x: next.clientX - origin.x, y: next.clientY - origin.y }, bounds) });
    const end = () => {
      head.removeEventListener("pointermove", move);
      head.removeEventListener("pointerup", end);
      head.removeEventListener("pointercancel", end);
    };
    head.addEventListener("pointermove", move);
    head.addEventListener("pointerup", end);
    head.addEventListener("pointercancel", end);
  }

  return (
    <div className="inline-layer">
      <MarginChips chips={chips} place={place} storageKey={`paperloom.chipOffsets.${paperId}`} />
      {open && openBase && (
        <div className="inline-window-host" style={{ ...openBase, left: openBase.left + openOffset.x, top: openBase.top + openOffset.y }}>
          <ThreadWindow item={open} threads={threads} onGrab={(event) => grab(event, open.key, openBase, openOffset)} {...handlers} />
        </div>
      )}
      {openNote && noteBase && (
        <div className="inline-window-host" style={{ ...noteBase, left: noteBase.left + noteOffset.x, top: noteBase.top + noteOffset.y }}>
          <NoteWindow
            note={openNote}
            onGrab={(event) => grab(event, noteKey, noteBase, noteOffset)}
            onCollapse={() => setOpenNoteId(null)}
            onShow={() => onShowNote(openNote.id)}
            onSave={(text) => onSaveNote(openNote.id, text)}
            onRemove={async () => {
              await onRemoveNote(openNote.id);
              setOpenNoteId(null);
            }}
          />
        </div>
      )}
      {draft && draftPlaced && (
        <div className="inline-window-host" style={windowStyle(draftPlaced, draft.kind === "note" ? 420 : WINDOW_WIDTH)}>
          {draft.kind === "ask" ? (
            <AskWindow onSend={handlers.onSendDraft} onClose={handlers.onCloseDraft} onToSidebar={handlers.onDraftToSidebar} />
          ) : (
            <MemoWindow quote={draft.quote} onSave={handlers.onSendDraft} onClose={handlers.onCloseDraft} />
          )}
        </div>
      )}
    </div>
  );
}

function windowStyle(placed: Placed, width = WINDOW_WIDTH) {
  const pageWidth = placed.pageRight - placed.pageLeft;
  const inset = Math.min(WINDOW_INSET, Math.max(0, (pageWidth - width) / 2));
  return { left: placed.pageLeft + inset, top: placed.bottom + 8, width: Math.min(width, Math.max(320, pageWidth - 2 * inset)) };
}

type WindowHandlers = Omit<
  Props,
  "paperId" | "threads" | "notes" | "onShowNote" | "onSaveNote" | "onRemoveNote" | "draft" | "place" | "layout" | "onSendDraft" | "onCloseDraft" | "onDraftToSidebar"
>;

function ThreadWindow({
  item,
  threads,
  onGrab,
  onMoveToSidebar,
  onSaveTranslation,
  onShowCitation,
  onShowAnchor,
  onShowBlock,
  onShowPage,
}: { item: InlineThread; threads: InlineThreads; onGrab: (event: PointerEvent<HTMLElement>) => void } & WindowHandlers) {
  const [question, setQuestion] = useState("");
  const [showOriginal, setShowOriginal] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const answers = item.answers ?? [];
  const translation = item.kind === "translate";
  const last = answers.at(-1);
  const { preferences, save } = usePreferences();
  // 번역 창 글꼴은 번역 창 머리에서 바꾼다(처음에는 글꼴 크기). 설정 화면에서는 뺐다(2026-10-04 사용자 요청: "설정에서 번역 크기 조정하는 건 빼")
  const translationFont = translation ? preferences.translation_font_size : null;
  const shownFont = translationFont ?? preferences.font_size;
  const resizeTranslation = (step: number) => {
    const size = Math.min(TRANSLATION_FONT.max, Math.max(TRANSLATION_FONT.min, shownFont + step));
    save({ translation_font_size: size }).catch(() => setNotice("글꼴 크기를 저장하지 못했습니다."));
  };

  useEffect(() => {
    const body = bodyRef.current;
    if (body) body.scrollTop = body.scrollHeight;
  }, [answers.length, item.pending?.text]);

  async function remove() {
    if (item.thread && !window.confirm("이 대화를 지울까요? 답도 함께 버립니다.")) return;
    await threads.remove(item.key).catch(() => setNotice("지우지 못했습니다."));
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = question.trim();
    if (!text || item.pending || !last) return;
    setQuestion("");
    void threads.followUp(item.key, text);
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  const original = item.anchor.display_quote ?? item.anchor.quote;
  return (
    <section
      className="inline-window"
      aria-label={`${item.title} 대화`}
      data-thread-key={item.key}
      data-kind={item.kind}
      style={translationFont === null ? undefined : ({ "--reading-font-size": `${translationFont}px` } as CSSProperties)}
    >
      <header className="inline-window-head" title="끌어서 옮기기" onPointerDown={onGrab}>
        <Icon name={KIND_ICONS[item.kind]} size={15} className="inline-window-icon" />
        <h3 className="inline-window-title">{translation ? `번역 · ${preferences.answer_language === "en" ? "English" : "한국어"}` : item.title}</h3>
        {translation && (
          <span className="inline-font-size" role="group" aria-label="번역 글꼴 크기">
            <button type="button" className="btn btn-icon inline-tool" aria-label="번역 글꼴 작게" title="글꼴 작게" disabled={shownFont <= TRANSLATION_FONT.min} onClick={() => resizeTranslation(-1)}>
              A−
            </button>
            <span className="inline-font-value">{shownFont}</span>
            <button type="button" className="btn btn-icon inline-tool" aria-label="번역 글꼴 크게" title="글꼴 크게" disabled={shownFont >= TRANSLATION_FONT.max} onClick={() => resizeTranslation(1)}>
              A+
            </button>
          </span>
        )}
        {translation ? (
          <button
            type="button"
            className="btn btn-icon inline-tool"
            aria-label="번역 복사"
            title="복사"
            disabled={!last}
            onClick={() => last && void navigator.clipboard?.writeText(formatMathForCopy(last.markdown, preferences.math_delimiters))}
          >
            <Icon name="copy" size={15} />
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-icon inline-tool"
            aria-label="사이드바로 옮기기"
            title="사이드바로 옮기기"
            disabled={!item.thread || item.pending !== null}
            onClick={() => onMoveToSidebar(item.key)}
          >
            <Icon name="toSidebar" size={15} />
          </button>
        )}
        <button type="button" className="btn btn-icon inline-tool" aria-label="삭제" title="삭제" disabled={item.pending !== null} onClick={() => void remove()}>
          <Icon name="trash" size={15} />
        </button>
        <button type="button" className="btn btn-icon inline-tool" aria-label="접기" title="접기" onClick={threads.collapse}>
          <Icon name="collapse" size={15} />
        </button>
      </header>
      {!translation && item.packet && <EvidenceSummary packet={item.packet} onShowAnchor={onShowAnchor} onShowBlock={onShowBlock} />}
      <div className="inline-window-body" ref={bodyRef} aria-live="polite">
        {answers.map((answer, index) => {
          const cite = (number: number, paragraph: number | null) => findCitation(answer.citations, number, paragraph);
          // 설명·번역의 첫 질문은 메뉴가 정한 문장이라 보이지 않는다. 직접 쓴 질문만 말풍선으로 보인다.
          const asked = item.kind === "ask" || index > 0;
          return (
            <div key={answer.answer_id} className="inline-turn" data-answer-id={answer.answer_id}>
              {asked && <p className="inline-question">{answer.prompt ?? answer.question}</p>}
              <div className="chat-answer">
                <AnswerMarkdown
                  markdown={answer.markdown}
                  canCite={(number, paragraph) => cite(number, paragraph) !== undefined}
                  onCite={(number, paragraph) => onShowCitation(cite(number, paragraph)!)}
                  onPage={onShowPage}
                />
              </div>
            </div>
          );
        })}
        {item.pending && (
          <div className="inline-turn is-pending">
            {(item.kind === "ask" || answers.length > 0) && <p className="inline-question">{item.pending.prompt}</p>}
            <div className="chat-answer">
              {item.pending.text ? (
                <AnswerMarkdown markdown={item.pending.text} canCite={() => false} onCite={() => undefined} />
              ) : (
                <p className="chat-thinking muted">답을 만드는 중…</p>
              )}
            </div>
            <button type="button" className="btn btn-ghost inline-stop" onClick={() => void threads.stop(item.key)} disabled={!item.pending.runId}>
              <Icon name="stop" size={12} /> 중단
            </button>
          </div>
        )}
        {translation && showOriginal && original && <blockquote className="inline-original">{original}</blockquote>}
        {item.answers === null && <p className="muted">대화를 불러오는 중…</p>}
        {(item.error || notice) && (
          <p className="status error" role="status">
            {item.error ?? notice}
          </p>
        )}
      </div>
      {translation ? (
        <footer className="inline-window-foot is-translation">
          <label className="switch">
            <input type="checkbox" checked={showOriginal} onChange={(event) => setShowOriginal(event.target.checked)} />
            <span className="switch-track" aria-hidden="true" />
            원문 함께 보기
          </label>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={!last}
            onClick={() =>
              last &&
              void onSaveTranslation(item, last.markdown)
                .then(() => setNotice(null))
                .catch(() => setNotice("주석으로 저장하지 못했습니다."))
            }
          >
            주석으로 저장
          </button>
        </footer>
      ) : (
        <form className="inline-window-foot" onSubmit={submit}>
          <textarea
            className="inline-input"
            aria-label="이어서 물어보기"
            rows={1}
            placeholder="이어서 물어보기…"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={onKeyDown}
            disabled={!last}
          />
          <button type="submit" className="send-button" aria-label="보내기" disabled={!question.trim() || item.pending !== null || !last}>
            <Icon name="arrowUp" size={16} />
          </button>
        </form>
      )}
    </section>
  );
}

/** 펼친 주석: 고른 글과 메모. 고치기(비우면 본문 표시만 남는다)·주석 패널에서 보기·삭제·접기, 머리를 끌어 옮긴다 */
function NoteWindow({
  note,
  onGrab,
  onCollapse,
  onShow,
  onSave,
  onRemove,
}: {
  note: NoteSpot;
  onGrab: (event: PointerEvent<HTMLElement>) => void;
  onCollapse: () => void;
  onShow: () => void;
  onSave: (text: string) => Promise<void>;
  onRemove: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(note.text);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    await onSave(text)
      .then(() => setEditing(false))
      .catch(() => setNotice("메모를 고치지 못했습니다."))
      .finally(() => setBusy(false));
  }

  async function remove() {
    if (!window.confirm("이 주석을 지울까요?")) return;
    await onRemove().catch(() => setNotice("지우지 못했습니다."));
  }

  return (
    <section className="inline-window note-window" aria-label="주석" data-note-id={note.id}>
      <header className="inline-window-head" title="끌어서 옮기기" onPointerDown={onGrab}>
        <Icon name="note" size={15} className="inline-window-icon" />
        <h3 className="inline-window-title">주석</h3>
        <button
          type="button"
          className="btn btn-icon inline-tool"
          aria-label="메모 고치기"
          title="메모 고치기"
          disabled={editing}
          onClick={() => {
            setText(note.text);
            setEditing(true);
          }}
        >
          <Icon name="pencil" size={15} />
        </button>
        <button type="button" className="btn btn-icon inline-tool" aria-label="주석 패널에서 보기" title="주석 패널에서 보기" onClick={onShow}>
          <Icon name="toSidebar" size={15} />
        </button>
        <button type="button" className="btn btn-icon inline-tool" aria-label="삭제" title="삭제" onClick={() => void remove()}>
          <Icon name="trash" size={15} />
        </button>
        <button type="button" className="btn btn-icon inline-tool" aria-label="접기" title="접기" onClick={onCollapse}>
          <Icon name="collapse" size={15} />
        </button>
      </header>
      <div className="inline-window-body">
        {note.quote && <blockquote className="inline-original">{note.quote}</blockquote>}
        {editing ? (
          <form className="note-edit" onSubmit={(event) => void save(event)}>
            <textarea
              className="ask-input"
              aria-label="메모"
              value={text}
              autoFocus
              rows={3}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => event.key === "Escape" && setEditing(false)}
            />
            <div className="ask-bar">
              <button type="button" className="btn btn-plain ask-close" onClick={() => setEditing(false)}>
                취소 <span className="kbd">Esc</span>
              </button>
              <button type="submit" className="btn btn-primary memo-save" disabled={busy}>
                저장
              </button>
            </div>
          </form>
        ) : (
          <p className="note-text">{note.text}</p>
        )}
        {notice && (
          <p className="status error" role="status">
            {notice}
          </p>
        )}
      </div>
    </section>
  );
}

function AskWindow({ onSend, onClose, onToSidebar }: { onSend: (text: string) => Promise<void>; onClose: () => void; onToSidebar: (text: string) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => inputRef.current?.focus(), []);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const question = text.trim();
    if (!question || busy) return;
    setBusy(true);
    await onSend(question).finally(() => setBusy(false));
  }
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Escape") onClose();
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };
  return (
    <form className="inline-window ask-window" aria-label="AI에게 질문" onSubmit={(event) => void submit(event)}>
      <textarea
        ref={inputRef}
        className="ask-input"
        aria-label="질문"
        placeholder="고른 부분에 대해 물어보세요"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={onKeyDown}
        rows={3}
      />
      <div className="ask-bar">
        <button type="button" className="btn btn-plain ask-close" onClick={onClose}>
          닫기 <span className="kbd">Esc</span>
        </button>
        <button type="button" className="btn btn-icon inline-tool" aria-label="사이드바 대화로 옮기기" title="사이드바 대화에 붙여 묻기" onClick={() => onToSidebar(text)}>
          <Icon name="toSidebar" size={15} />
        </button>
        <span className="ask-hint">선택한 글과 앞뒤 문단을 함께 보냅니다</span>
        <button type="submit" className="send-button" aria-label="질문 보내기" disabled={!text.trim() || busy}>
          <Icon name="arrowUp" size={16} />
        </button>
      </div>
    </form>
  );
}

function MemoWindow({ quote, onSave, onClose }: { quote: string; onSave: (text: string) => Promise<void>; onClose: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => inputRef.current?.focus(), []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    await onSave(text).finally(() => setBusy(false));
  }
  return (
    <form className="inline-window memo-window" aria-label="주석 쓰기" onSubmit={(event) => void submit(event)}>
      {quote && <blockquote className="inline-original">{quote}</blockquote>}
      <textarea
        ref={inputRef}
        className="ask-input"
        aria-label="메모"
        placeholder="메모 (비워 두면 표시만 남깁니다)"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => event.key === "Escape" && onClose()}
        rows={3}
      />
      <div className="ask-bar">
        <button type="button" className="btn btn-plain ask-close" onClick={onClose}>
          닫기 <span className="kbd">Esc</span>
        </button>
        <button type="submit" className="btn btn-primary memo-save" disabled={busy}>
          주석 저장
        </button>
      </div>
    </form>
  );
}
