import { relativeTime } from "../../shared/time";
import { REGION_KIND_LABELS as REGION_LABELS } from "../annotations/api";
import { THREAD_KIND_LABELS } from "./api";
import { answerCount, excerpt, type InlineThread, lastAnswerAt } from "./useInlineThreads";

type Props = Readonly<{
  items: readonly InlineThread[];
  active: string | null;
  onOpen: (item: InlineThread) => void;
}>;

/**
 * 사이드바 "선택 설명·질문" (시안 3d). 이 논문에서 고른 곳에 열었던 설명·번역·질문 대화 목록이다.
 * 누르면 원문 위치에서 창을 펼친다. 사이드바로 옮긴 대화는 사이드바 대화에서 연다.
 */
export function ThreadsPanel({ items, active, onOpen }: Props) {
  const ordered = [...items].sort((a, b) => (b.thread?.created_at ?? "￿").localeCompare(a.thread?.created_at ?? "￿"));
  return (
    <section className="side-section" aria-labelledby="threads-heading">
      <header className="side-head is-strong">
        <h2 id="threads-heading" className="side-title">
          선택 설명·질문
        </h2>
        <span className="side-note">누르면 원문 위치에서 열림</span>
      </header>
      {ordered.length === 0 ? (
        <p className="side-empty muted">본문에서 글이나 그림을 고르고 설명·번역·AI에게 질문을 누르면 여기에 모입니다.</p>
      ) : (
        <ol className="thread-list">
          {ordered.map((item) => {
            const count = answerCount(item);
            const last = lastAnswerAt(item);
            const when = last ? relativeTime(last) : "방금";
            const quote =
              item.anchor.kind === "text" ? excerpt(item.anchor.display_quote ?? item.anchor.quote, 120) : `[${REGION_LABELS[item.anchor.kind] ?? "고른"} 영역]`;
            return (
              <li key={item.key}>
                <button
                  type="button"
                  className={item.key === active ? "thread-row is-active" : "thread-row"}
                  onClick={() => onOpen(item)}
                  data-thread-key={item.key}
                >
                  <span className="thread-page">p.{item.anchor.page_index + 1}</span>
                  <span className="thread-main">
                    <span className="thread-meta">
                      <span className={item.kind === "ask" ? "tag tag-outline" : "tag tag-neutral"}>{THREAD_KIND_LABELS[item.kind]}</span>
                      {when} · 답변 {count}
                      {item.thread?.placement === "sidebar" && " · 사이드바 대화"}
                    </span>
                    <span className="thread-title">{item.title}</span>
                    <span className="thread-quote">{quote}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
