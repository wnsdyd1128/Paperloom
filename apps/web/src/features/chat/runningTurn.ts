/**
 * 답을 만드는 중인 사이드바 대화 차례(논문마다 하나). 대화 칸(ChatPanel)이 아니라 이 모듈이 들고 있어, 답을 받는 중에
 * 서재로 나갔다 돌아와도(대화 칸이 새로 만들어져도) 만드는 중인 답을 이어 보이고, 끝나면 그 답을 대화에 더한다
 * (2026-11-08 사용자 보고: 답을 받는 중에 나가면 돌아와도 그 대화가 대화 기록에 없었다). 브리지는 브라우저가 끊겨도 답을
 * 끝까지 만들어 저장하고, 이 탭은 나가도 브리지에서 답을 계속 받는다. 이 탭 안에서만 이어진다: 새로고침하면 만드는 중인
 * 차례는 보이지 않고, 저장된 뒤 다시 열면 보인다. 차례가 도는 동안 같은 논문에서 또 묻지 않는다(브리지도 한 번에 한 차례다).
 */
import { useSyncExternalStore } from "react";

import type { Answer, AnswerContext } from "../answers/api";
import type { AttachedImage } from "./chatImages";
import type { ForkDraft } from "./sessions";

export type RunningTurn = Readonly<{
  prompt: string;
  quote: readonly AnswerContext[];
  /** 질문에 붙인 이미지. 중단하면 입력칸에 돌려 둔다 */
  images: readonly AttachedImage[];
  /** 지금까지 받은 답 */
  text: string;
  /** 중단에 쓰는 실행 ID. 브리지가 주기 전에는 null */
  runId: string | null;
  /** 묻는 대화. 새 대화·갈래의 첫 질문이면 null */
  session: string | null;
  /** 갈래의 첫 질문이면 그 갈래 */
  fork: ForkDraft | null;
}>;

/** 차례가 끝난 결과: 답을 저장했거나, 중단했거나(저장하지 않음), 실패했다 */
export type TurnOutcome =
  | Readonly<{ kind: "done"; answer: Answer }>
  | Readonly<{ kind: "cancelled" }>
  | Readonly<{ kind: "error"; message: string }>;

type FinishListener = (paperId: string, turn: RunningTurn, outcome: TurnOutcome) => void;

const turns = new Map<string, RunningTurn>();
const changeListeners = new Set<() => void>();
const finishListeners = new Set<FinishListener>();

export function runningTurn(paperId: string): RunningTurn | null {
  return turns.get(paperId) ?? null;
}

export function startTurn(paperId: string, turn: RunningTurn): void {
  turns.set(paperId, turn);
  changed();
}

export function updateTurn(paperId: string, update: (turn: RunningTurn) => RunningTurn): void {
  const turn = turns.get(paperId);
  if (!turn) return;
  turns.set(paperId, update(turn));
  changed();
}

/** 차례를 끝낸다. 끝난 차례를 듣는 곳(그 논문의 대화 칸·답변 화면)이 먼저 결과를 받고, 그다음 만드는 중 표시가 사라진다. */
export function finishTurn(paperId: string, outcome: TurnOutcome): void {
  const turn = turns.get(paperId);
  if (!turn) return;
  for (const listener of finishListeners) listener(paperId, turn, outcome);
  turns.delete(paperId);
  changed();
  if (outcome.kind === "done") {
    const channel = savedChannel();
    channel?.postMessage(paperId);
    channel?.close(); // 보낸 소식은 닫아도 간다
  }
}

export function onTurnFinished(listener: FinishListener): () => void {
  finishListeners.add(listener);
  return () => void finishListeners.delete(listener);
}

/**
 * 대화 차례가 답을 저장했을 때. 이 탭의 차례뿐 아니라 다른 탭(사이드바에서 분리한 대화 탭)의 차례도 알린다: 대화를 분리해도
 * 답변 화면이 그 답을 목록에 넣는다(2026-11-08 사용자 보고).
 */
export function onAnswerSaved(listener: (paperId: string) => void): () => void {
  const channel = savedChannel();
  // 같은 탭의 차례도 채널로 온다(보낸 채널 객체에만 오지 않는다). 채널이 없는 브라우저면 이 탭의 차례만 듣는다
  if (!channel) {
    return onTurnFinished((paperId, _turn, outcome) => {
      if (outcome.kind === "done") listener(paperId);
    });
  }
  channel.onmessage = (event: MessageEvent<string>) => listener(event.data);
  return () => channel.close();
}

function savedChannel(): BroadcastChannel | null {
  return typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("paperloom-answer-saved");
}

/** 그 논문에서 만드는 중인 차례. 바뀌면 다시 그린다. */
export function useRunningTurn(paperId: string): RunningTurn | null {
  return useSyncExternalStore(subscribe, () => runningTurn(paperId));
}

function subscribe(listener: () => void): () => void {
  changeListeners.add(listener);
  return () => void changeListeners.delete(listener);
}

function changed(): void {
  for (const listener of changeListeners) listener();
}
