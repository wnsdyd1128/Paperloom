/**
 * 만드는 중인 답 (사이드바 대화 칸·원문 위 질문 창). Motion Studies의 "Goo Thinking"과 "Streaming Reply"를 이었다.
 * 첫 글자를 받기 전에는 점 셋이 goo 필터 안에서 차례로 튀고, 첫 글자가 오면 점이 한 방울로 모여 가라앉은 뒤 판이
 * 답 너비로 열린다. 그다음 답은 낱말마다 아래에서 올라오며 흐림이 걷히고(answers/streamWords.ts), 칸 높이는 spring으로
 * 따라 늘어난다. Paperloom의 답에는 바탕이 없으므로 회색 판은 열리면서 투명해진다(저장된 답과 같은 모습으로 끝난다).
 * 원본의 자동 시연(정해 둔 질문과 답을 되풀이)은 뺐고, 실제로 받는 답만 그린다.
 */
import "./chatMotion.css";

import { type CSSProperties, useEffect, useId, useLayoutEffect, useRef } from "react";

import { clamp, reducedMotion, spring, springEasing, startLoop, step, tune } from "../../shared/spring";
import { AnswerMarkdown } from "../answers/AnswerMarkdown";

/** 낱말 하나 (원본 340/26), 질문·판이 올라오기 (원본 300/22) */
const WORD = springEasing(340, 26);
const RISE = springEasing(300, 22);
export const MOTION_STYLE = {
  "--word-ease": WORD.easing,
  "--word-time": `${WORD.duration.toFixed(3)}s`,
  "--rise-ease": RISE.easing,
  "--rise-time": `${RISE.duration.toFixed(3)}s`,
} as CSSProperties;

/** 낱말이 나타나는 간격(원본 0.07초)과 받은 글보다 늦어도 되는 최대 시간 */
const WORD_GAP = 70;
const MAX_LAG = 600;
const PILL = { width: 64, height: 40 };

type Props = Readonly<{
  text: string;
  /** 칸 높이가 늘 때마다 (대화 칸은 맨 아래로 내린다) */
  onGrow?: () => void;
}>;

export function StreamingAnswer({ text, onGrow }: Props) {
  const filter = `goo-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
  const box = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const motion = useRef<Motion | null>(null);
  const grow = useRef(onGrow);
  grow.current = onGrow;
  const nextAt = useRef(0);
  const started = text !== "";

  useEffect(() => {
    const begun = startMotion(box.current!, body.current!, started, () => grow.current?.());
    motion.current = begun;
    return begun.stop;
  }, []);

  useEffect(() => {
    if (started) motion.current?.answer();
  }, [started]);

  // 새로 온 낱말에 차례로 늦춤을 준다. 받은 글이 빨리 오면 늦춤이 MAX_LAG를 넘지 않게 함께 나타난다
  useLayoutEffect(() => {
    const now = performance.now();
    for (const word of body.current?.querySelectorAll<HTMLElement>(".stream-word:not([data-shown])") ?? []) {
      const delay = Math.min(Math.max(0, nextAt.current - now), MAX_LAG);
      nextAt.current = now + delay + WORD_GAP;
      word.style.animationDelay = `${Math.round(delay)}ms`;
      word.dataset.shown = "";
    }
  }, [text]);

  return (
    <div ref={box} className="chat-stream" data-open={started || undefined} style={MOTION_STYLE}>
      <svg className="chat-goo-defs" width="0" height="0" aria-hidden="true" focusable="false">
        <filter id={filter} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="3.2" result="b" />
          <feColorMatrix in="b" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 20 -8" />
        </filter>
      </svg>
      <div className="chat-goo" style={{ filter: `url(#${filter})` }} aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      {!started && <p className="chat-thinking sr-only">답을 만드는 중…</p>}
      <div ref={body} className="chat-stream-body">
        {started && <AnswerMarkdown markdown={text} canCite={() => false} onCite={() => undefined} streaming />}
      </div>
    </div>
  );
}

type Motion = Readonly<{ answer: () => void; stop: () => void }>;

function startMotion(box: HTMLElement, body: HTMLElement, open: boolean, onGrow: () => void): Motion {
  const reduce = reducedMotion();
  const S = (x: number, stiffness: number, damping: number) => spring(x, stiffness, damping, reduce);
  const holder = box.parentElement ?? box;
  const full = () => holder.clientWidth;
  body.style.width = `${full()}px`; // 판이 좁은 동안에도 답은 다 열린 너비로 놓아 높이를 잰다
  // 원본 think.js와 같은 값: 점(x 300/22, y 420/14), 판(240/24), 가라앉기(300/26), 답(260/28), 한 방울(300/24)
  const dots = [...box.querySelectorAll<HTMLElement>(".chat-goo i")].map((el, i) => ({ el, x: S(19 + i * 13, 300, 22), y: S(0, 420, 14) }));
  const W = S(open ? full() : PILL.width, 240, 24);
  const H = S(open ? body.offsetHeight : PILL.height, 240, 24);
  const drop = S(open ? 0 : 1, 300, 26);
  const A = S(open ? 1 : 0, 260, 28);
  const big = S(1, 300, 24);
  const springs = [W, H, drop, A, big, ...dots.flatMap((dot) => [dot.x, dot.y])];

  let phase: "think" | "merge" | "answer" = open ? "answer" : "think";
  let clock = 0;
  let hop = 0.3;
  let hops = 0;
  let sinkAt = Infinity;
  let openAt = Infinity;
  let showAt = Infinity;
  let settleAt = Infinity;
  let lastHeight = H.x;

  const measure = () => {
    body.style.width = `${full()}px`;
    if (phase !== "answer") return;
    W.t = full();
    H.t = body.offsetHeight;
  };
  const observer = new ResizeObserver(measure);
  observer.observe(holder);
  observer.observe(body);
  measure();

  function answer() {
    if (phase !== "think") return;
    phase = "merge";
    for (const dot of dots) {
      dot.x.t = 32 - 4.5; // 가운데로 모인다
      dot.y.t = 0;
    }
    big.t = 1.45;
    sinkAt = clock + 0.45;
    openAt = clock + 0.6;
  }

  function frame(dt: number) {
    clock += dt;
    // 점은 왼쪽부터 하나씩 튀고 잠깐 쉰다
    if (phase === "think" && (hop -= dt) <= 0) {
      dots[hops % 3].y.v = -95;
      hops++;
      hop = hops % 3 ? 0.16 : 0.46;
    }
    if (clock >= sinkAt) {
      sinkAt = Infinity;
      drop.t = 0;
    }
    if (clock >= openAt) {
      openAt = Infinity;
      phase = "answer";
      measure();
      showAt = clock + 0.12;
      settleAt = clock + 0.6;
    }
    if (clock >= showAt) {
      showAt = Infinity;
      A.t = 1;
    }
    if (clock >= settleAt) {
      // 열린 뒤 글이 늘 때는 Streaming Reply의 말풍선 spring(260/26)으로 따라간다
      settleAt = Infinity;
      tune(W, 260, 26, reduce);
      tune(H, 260, 26, reduce);
    }
    for (const s of springs) step(s, dt);
  }

  function render() {
    box.style.width = `${W.x.toFixed(2)}px`;
    box.style.height = `${Math.max(0, H.x).toFixed(2)}px`;
    // 판 바탕은 답 너비로 열리는 만큼 사라진다
    box.style.setProperty("--pill", clamp(1 - (W.x - PILL.width) / Math.max(1, full() - PILL.width), 0, 1).toFixed(3));
    const scale = clamp(drop.x, 0, 1.2) * big.x;
    for (const dot of dots) dot.el.style.transform = `translate(${dot.x.x.toFixed(2)}px,${(15.5 + dot.y.x).toFixed(2)}px) scale(${scale.toFixed(3)})`;
    body.style.opacity = clamp(A.x, 0, 1).toFixed(3);
    body.style.transform = `translateY(${((1 - A.x) * 8).toFixed(2)}px)`;
    if (Math.abs(H.x - lastHeight) > 0.5) {
      lastHeight = H.x;
      onGrow();
    }
  }

  const stopLoop = startLoop(frame, render);
  return {
    answer,
    stop: () => {
      stopLoop();
      observer.disconnect();
    },
  };
}
