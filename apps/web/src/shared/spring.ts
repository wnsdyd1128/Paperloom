/**
 * 화면 움직임에 쓰는 spring. Motion Studies(designbookmark.com/motion)의 shared/motion.js를 옮겼다. 원본 컴포넌트와
 * 똑같이 움직이도록 적분 방식(반암시적 Euler, 한 화면을 4번 나눠 적분, 한 화면은 최대 1/30초)을 그대로 둔다.
 * 값은 (stiffness, damping) 쌍이고, 각 컴포넌트는 원본이 쓴 값을 그대로 쓴다.
 */
export type Spring = { x: number; v: number; t: number; k: number; c: number };

/** 한 화면을 나눠 적분하는 횟수와 한 화면의 최대 시간(초). 탭이 멈췄다 돌아와도 튀지 않는다. */
export const SUBSTEPS = 4;
export const MAX_FRAME = 1 / 30;

export const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));

/** 운영체제의 "움직임 줄이기" */
export function reducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** 원본 S(x, k, c)와 같다. reduce면 원본 tune()처럼 임계 감쇠(2√k)로 바꿔 넘치지 않게 한다. */
export function spring(x: number, stiffness: number, damping: number, reduce = false): Spring {
  return { x, v: 0, t: x, k: stiffness, c: reduce ? 2 * Math.sqrt(stiffness) : damping };
}

/** 원본 tune(): 같은 spring을 다른 느낌으로 바꾼다(예: 끄는 동안과 놓은 뒤). */
export function tune(s: Spring, stiffness: number, damping: number, reduce = false): void {
  s.k = stiffness;
  s.c = reduce ? 2 * Math.sqrt(stiffness) : damping;
}

export function step(s: Spring, dt: number): void {
  const a = -s.k * (s.x - s.t) - s.c * s.v;
  s.v += a * dt;
  s.x += s.v * dt;
}

/** 한 화면마다 frame을 SUBSTEPS번 나눠 부르고 render를 한 번 부른다(원본 한 rAF 고리). 멈추는 함수를 돌려준다. */
export function startLoop(frame: (dt: number) => void, render: () => void): () => void {
  let last = performance.now();
  let id = requestAnimationFrame(function loop(now: number) {
    const dt = clamp((now - last) / 1000, 0, MAX_FRAME);
    last = now;
    for (let i = 0; i < SUBSTEPS; i++) frame(dt / SUBSTEPS);
    render();
    id = requestAnimationFrame(loop);
  });
  return () => cancelAnimationFrame(id);
}

/**
 * 0에서 1로 가는 spring을 CSS linear() easing으로 옮긴다(같은 적분을 1/60초마다 적는다). 낱말처럼 수가 많고
 * 한 번 나타나고 마는 것은 JS 고리 대신 CSS animation으로 같은 곡선을 그린다. duration은 초다.
 */
export function springEasing(stiffness: number, damping: number): Readonly<{ easing: string; duration: number }> {
  const s = spring(0, stiffness, damping);
  s.t = 1;
  const points = [0];
  for (let frame = 0; frame < 240; frame++) {
    for (let i = 0; i < SUBSTEPS; i++) step(s, 1 / 60 / SUBSTEPS);
    points.push(s.x);
    if (Math.abs(s.x - 1) < 1e-3 && Math.abs(s.v) < 1e-2) break;
  }
  points[points.length - 1] = 1;
  return { easing: `linear(${points.map((point) => Number(point.toFixed(4))).join(", ")})`, duration: (points.length - 1) / 60 };
}
