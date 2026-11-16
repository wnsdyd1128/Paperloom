/**
 * 대화 입력부의 움직임 (Motion Studies "Prompt Box"를 옮겼다). 입력칸 높이가 글을 따라 spring으로 늘고 줄며(420/34),
 * 답을 만드는 동안 보내기 화살표가 돌며 작아지고 중단 사각형이 커진다(520/30). 입력칸 위 상태 줄은 답을 만드는 동안
 * 열려 있고(380/30), 끝나면 결과를 1.6초 보인 뒤 닫힌다. 원본의 자동 입력 시연은 실제 입력과 헷갈리므로 뺐다.
 * 입력칸의 최소·최대 높이는 CSS(.chat-input의 min-height·max-height)가 정한다.
 */
import { type RefObject, useEffect, useRef } from "react";

import { clamp, reducedMotion, spring, startLoop, step } from "../../shared/spring";

/** 상태 줄: 답을 만드는 중(생각·쓰기)과 끝난 결과. null이면 닫혀 있다 */
export type PromptStatus = "thinking" | "writing" | "done" | "cancelled" | "error" | null;

export const PROMPT_STATUS_LABELS: Record<Exclude<PromptStatus, null>, string> = {
  thinking: "Claude가 생각하는 중",
  writing: "답을 쓰는 중",
  done: "답을 마쳤습니다",
  cancelled: "중단했습니다",
  error: "답을 받지 못했습니다",
};

/** 상태 줄 높이(px)와 입력부 상자의 간격(.chat-composer-box gap) */
const STATUS_HEIGHT = 26;
const BOX_GAP = 6;
/** 끝난 결과를 보이는 시간과 닫힌 뒤 비우기까지(초, 원본 1.6·0.7) */
const SHOW_RESULT = 1.6;
const CLOSE_TIME = 0.7;

type Refs = Readonly<{
  input: RefObject<HTMLTextAreaElement | null>;
  status: RefObject<HTMLElement | null>;
  arrow: RefObject<HTMLElement | null>;
  square: RefObject<HTMLElement | null>;
}>;

type State = Readonly<{
  question: string;
  busy: boolean;
  status: PromptStatus;
  /** 끝난 결과를 다 보이고 상태 줄이 닫혔다 */
  onStatusClosed: () => void;
}>;

type Motion = Readonly<{ fit: () => void; busy: (on: boolean) => void; status: (status: PromptStatus) => void; stop: () => void }>;

export function usePromptBox(refs: Refs, { question, busy, status, onStatusClosed }: State) {
  const motion = useRef<Motion | null>(null);
  const closed = useRef(onStatusClosed);
  closed.current = onStatusClosed;

  useEffect(() => {
    const begun = startMotion(refs, () => closed.current());
    motion.current = begun;
    return begun.stop;
  }, []);

  useEffect(() => motion.current?.fit(), [question]);
  useEffect(() => motion.current?.busy(busy), [busy]);
  useEffect(() => motion.current?.status(status), [status]);
}

function startMotion(refs: Refs, onStatusClosed: () => void): Motion {
  const reduce = reducedMotion();
  const input = refs.input.current!;
  const line = refs.status.current!;
  const arrow = refs.arrow.current!;
  const square = refs.square.current!;
  const S = (x: number, stiffness: number, damping: number) => spring(x, stiffness, damping, reduce);
  const H = S(input.offsetHeight, 420, 34); // 입력칸 높이
  const SH = S(0, 380, 30); // 상태 줄, 0 닫힘 1 열림
  const M = S(0, 520, 30); // 단추, 0 화살표 1 중단
  let clock = 0;
  let closeAt = Infinity;
  let clearAt = Infinity;
  let max = Infinity;

  function fit() {
    const style = getComputedStyle(input);
    const min = parseFloat(style.minHeight) || 0;
    max = parseFloat(style.maxHeight) || Infinity;
    const shown = input.style.height;
    input.style.height = "auto";
    H.t = clamp(input.scrollHeight, min, max);
    input.style.height = shown;
  }

  function status(next: PromptStatus) {
    closeAt = Infinity;
    clearAt = Infinity;
    if (next === null) SH.t = 0;
    else {
      SH.t = 1;
      if (next === "done" || next === "cancelled" || next === "error") closeAt = clock + SHOW_RESULT;
    }
  }

  function frame(dt: number) {
    clock += dt;
    if (clock >= closeAt) {
      closeAt = Infinity;
      SH.t = 0;
      clearAt = clock + CLOSE_TIME;
    }
    if (clock >= clearAt) {
      clearAt = Infinity;
      onStatusClosed();
    }
    step(H, dt);
    step(SH, dt);
    step(M, dt);
  }

  function render() {
    input.style.height = `${H.x.toFixed(2)}px`;
    // 최대 높이에 닿았을 때만 입력칸 안에서 스크롤한다(늘어나는 동안 스크롤 막대가 깜빡이지 않게)
    input.style.overflowY = H.t >= max - 0.5 ? "auto" : "hidden";
    const open = Math.max(0, SH.x);
    line.style.height = `${(open * STATUS_HEIGHT).toFixed(2)}px`;
    line.style.marginBottom = `${((Math.min(1, open) - 1) * BOX_GAP).toFixed(2)}px`;
    line.style.opacity = clamp(SH.x, 0, 1).toFixed(3);
    const m = clamp(M.x, 0, 1.2);
    arrow.style.transform = `scale(${Math.max(0, 1 - m).toFixed(3)}) rotate(${(m * 90).toFixed(1)}deg)`;
    square.style.transform = `scale(${Math.max(0, m).toFixed(3)})`;
  }

  fit();
  H.x = H.t; // 처음에는 늘이지 않고 맞춘다
  const stopLoop = startLoop(frame, render);
  return {
    fit,
    busy: (on) => {
      M.t = on ? 1 : 0;
    },
    status,
    stop: stopLoop,
  };
}
