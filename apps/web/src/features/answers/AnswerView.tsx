import { EVIDENCE_ROLE_LABELS } from "../context/api";
import { formatTime } from "../../shared/time";
import type { Answer, Citation } from "./api";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { findCitation } from "./citations";

type Props = Readonly<{
  answer: Answer;
  onShowCitation: (citation: Citation) => void;
  onDiscard: (answer: Answer) => void;
}>;

/**
 * AI가 쓴 답변 하나 (ADR 0002·0003). 검토 전 답변이라 그렇게 표시한다. 본문은 Markdown으로 그리되 HTML은 해석하지
 * 않는다(PLAN A08, AnswerMarkdown). 근거 번호는 본문 안에서 눌러 원문 위치로 간다.
 */
export function AnswerView({ answer, onShowCitation, onDiscard }: Props) {
  const cite = (number: number, paragraph: number | null) => findCitation(answer.citations, number, paragraph);
  return (
    <article className="answer" data-answer-id={answer.answer_id}>
      <p className="muted">
        {source(answer)} · {formatTime(answer.created_at)}
      </p>
      {answer.prompt && <p className="answer-prompt">질문: {answer.prompt}</p>}
      <div className="answer-text">
        <AnswerMarkdown
          markdown={answer.markdown}
          canCite={(number, paragraph) => cite(number, paragraph) !== undefined}
          onCite={(number, paragraph) => onShowCitation(cite(number, paragraph)!)}
        />
      </div>
      {answer.citations.length > 0 && (
        <p className="muted answer-citations">
          근거:{" "}
          {answer.citations
            .map((citation) => `근거 ${citation.number} · ${EVIDENCE_ROLE_LABELS[citation.role] ?? "고른 영역"} · ${citation.page_index + 1}쪽`)
            .join(", ")}
        </p>
      )}
      {answer.unresolved_citations.length > 0 && (
        <p className="status error">
          packet에 없는 근거 번호: {answer.unresolved_citations.map((number) => `근거 ${number}`).join(", ")}
        </p>
      )}
      <button
        type="button"
        className="link-button"
        onClick={() => {
          if (window.confirm("이 답변을 버릴까요? 목록에서 사라집니다.")) onDiscard(answer);
        }}
      >
        답변 버리기
      </button>
    </article>
  );
}

function source(answer: Answer): string {
  return answer.origin === "claude_code" ? "Claude Code 대화(이 PC)" : `${answer.connection_name ?? "AI 호스트"}가 저장`;
}
