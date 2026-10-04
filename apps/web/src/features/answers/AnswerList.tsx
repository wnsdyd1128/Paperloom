import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../shared/http";
import { type Answer, type Citation, discardAnswer, listAnswers } from "./api";
import { AnswerView } from "./AnswerView";

const POLL_MS = 5000;

type Props = Readonly<{
  /** 이 packet의 답변만. 없으면 모든 packet의 최근 답변 */
  packetId?: string;
  onShowCitation: (citation: Citation) => void;
  /** 답변이 새로 들어오거나 빠졌다 (packet 상태가 IMPORTED로 바뀌었을 수 있다) */
  onChanged?: () => void;
  /** 답변이 없을 때의 안내. 없으면 아무것도 보이지 않는다 */
  emptyText?: string;
  /** 이 출처의 답변은 보이지 않는다 (대화 탭이 따로 보이는 Claude Code 답변). 바뀌었는지는 함께 본다 */
  hideOrigin?: Answer["origin"];
}>;

/** 호스트가 저장한 답변 목록. 호스트는 언제든 저장할 수 있으므로 주기적으로 다시 받는다. */
export function AnswerList({ packetId, onShowCitation, onChanged, emptyText, hideOrigin }: Props) {
  const [answers, setAnswers] = useState<readonly Answer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const seen = useRef<string | null>(null); // 처음 받은 뒤의 답변 ID들
  const changed = useRef(onChanged);
  changed.current = onChanged;

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      listAnswers({ packetId })
        .then((next) => {
          if (cancelled) return;
          const ids = next.map((answer) => answer.answer_id).join(",");
          if (seen.current !== null && ids !== seen.current) changed.current?.();
          seen.current = ids;
          setAnswers(next.filter((answer) => answer.origin !== hideOrigin));
        })
        .catch(() => undefined);
    seen.current = null;
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [packetId, hideOrigin]);

  async function discard(answer: Answer) {
    setError(null);
    try {
      await discardAnswer(answer.answer_id);
      setAnswers((current) => current.filter((item) => item.answer_id !== answer.answer_id));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "버리지 못했습니다. 백엔드 연결을 확인하세요.");
    }
  }

  if (answers.length === 0 && !error) return emptyText ? <p className="muted">{emptyText}</p> : null;
  return (
    <div className="answer-list">
      {answers.map((answer) => (
        <AnswerView key={answer.answer_id} answer={answer} onShowCitation={onShowCitation} onDiscard={(item) => void discard(item)} />
      ))}
      {error && (
        <p className="status error" role="status">
          {error}
        </p>
      )}
    </div>
  );
}
