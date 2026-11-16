/**
 * PDF 받침: 서재가 비었을 때 표 자리에 놓고, 창 위로 PDF를 끌거나 올리는 동안에는 화면 가운데에 띄운다.
 * Motion Studies "File Drop"(designbookmark.com/motion)을 Paperloom 색·글꼴·모서리(0)로 옮겼다. 파일이 다가오면
 * 바탕이 물들고 화살표가 까딱이고, 놓으면 원이 삼킨다. 서버가 PDF를 확인하는 동안 고리가 돌고, 등록되면 원이 초록으로
 * 차며 체크가 그려진다. 원본의 자동 시연(가짜 파일 칩을 끌고 와 올리는 척하기)은 실제 올리기와 헷갈리므로 뺐다.
 *
 * 움직임은 React 상태 대신 requestAnimationFrame에서 style을 직접 바꾼다. 굴러 바뀌는 두 줄의 글도 직접 그리므로
 * 화면 낭독기에서는 숨기고, 올리기 안내는 서재의 notice(role=status)가 알린다.
 */
import "./fileDrop.css";

import { type KeyboardEvent, useEffect, useRef } from "react";

import { Icon } from "../../shared/Icon";
import { clamp, reducedMotion, type Spring, spring, startLoop, step } from "../../shared/spring";
import { type DropText, dropText } from "./dropText";
import type { UploadStatus } from "./useLibrary";

/** 등록·실패를 보여 주는 시간(초, 원본 2.6). 그 뒤 onSettled로 받침을 처음 모습으로 되돌린다. */
const HOLD = 2.6;
const RING = 2 * Math.PI * 33;
/** 서버가 확인하는 동안 도는 고리의 길이(원둘레 비율)와 도는 빠르기(도/초) */
const SPIN_ARC = 0.28;
const SPIN_SPEED = 300;

type Props = Readonly<{
  status: UploadStatus;
  /** 파일을 창 위로 끌고 있다 */
  near: boolean;
  /** 있으면 누르기·Enter·Space로 파일 고르기 창을 연다(서재가 비었을 때의 받침) */
  onPick?: () => void;
  /** 등록·실패를 다 보여 줬다 */
  onSettled: () => void;
}>;

export function FileDrop({ status, near, onPick, onSettled }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const motion = useRef<Motion | null>(null);
  const settled = useRef(onSettled);
  settled.current = onSettled;
  const pickable = onPick !== undefined;

  useEffect(() => {
    const started = startMotion(root.current!, () => settled.current());
    motion.current = started;
    return () => {
      started.stop();
      motion.current = null;
    };
  }, []);

  useEffect(() => {
    motion.current?.show(status, near, dropText(status, near, pickable));
  }, [status, near, pickable]);

  const pick = () => {
    if (status.kind === "idle") onPick?.();
  };
  const controls = onPick
    ? {
        role: "button" as const,
        tabIndex: 0,
        "aria-label": "PDF 등록: 여기에 끌어다 놓거나 눌러서 파일을 고릅니다",
        "aria-disabled": status.kind !== "idle" || undefined,
        onClick: pick,
        onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          pick();
        },
        onPointerDown: () => motion.current?.press(),
      }
    : { "aria-hidden": true };

  return (
    <div ref={root} className="file-drop" data-phase={status.kind} {...controls}>
      <div className="file-drop-core">
        <i className="file-drop-flood" />
        <svg className="file-drop-ring" viewBox="0 0 72 72" fill="none" strokeWidth="3" strokeLinecap="round" aria-hidden="true">
          <circle className="file-drop-track" cx="36" cy="36" r="33" />
          <circle className="file-drop-arc" cx="36" cy="36" r="33" strokeDasharray={RING.toFixed(2)} />
        </svg>
        <span className="file-drop-icon file-drop-up">
          <Icon name="upload" size={26} />
        </span>
        <span className="file-drop-icon file-drop-doc">
          <Icon name="fileText" size={26} />
        </span>
        <span className="file-drop-icon file-drop-ok">
          {/* Lucide check를 짧은 획부터 그리도록 뒤집은 선. 길이 22.6 < dasharray 24 */}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 12l5 5L20 6" />
          </svg>
        </span>
      </div>
      <div className="file-drop-line file-drop-title" aria-hidden="true" />
      <div className="file-drop-line file-drop-detail" aria-hidden="true" />
    </div>
  );
}

type Motion = Readonly<{
  show: (status: UploadStatus, near: boolean, text: DropText) => void;
  press: () => void;
  stop: () => void;
}>;

/** 굴러 바뀌는 한 줄: 옛 글은 위로 빠지고 새 글이 아래에서 올라온다(원본 line/say). */
type Line = { readonly el: HTMLElement; cur: HTMLSpanElement | null; old: HTMLSpanElement | null; readonly o: Spring };

function startMotion(zone: HTMLElement, onSettled: () => void): Motion {
  const need = <T extends Element>(selector: string): T => {
    const found = zone.querySelector<T>(selector);
    if (!found) throw new Error(`FileDrop: ${selector} 없음`);
    return found;
  };
  const core = need<HTMLElement>(".file-drop-core");
  const flood = need<HTMLElement>(".file-drop-flood");
  const ring = need<SVGSVGElement>(".file-drop-ring");
  const arc = need<SVGCircleElement>(".file-drop-arc");
  const up = need<HTMLElement>(".file-drop-up");
  const doc = need<HTMLElement>(".file-drop-doc");
  const ok = need<HTMLElement>(".file-drop-ok");
  const tick = need<SVGPathElement>(".file-drop-ok path");

  const reduce = reducedMotion();
  const S = (x: number, stiffness: number, damping: number) => spring(x, stiffness, damping, reduce);
  // 원본 drop.js와 같은 값 (stiffness, damping)
  const ZS = S(1, 380, 16); // 받침 크기
  const ZH = S(0, 300, 26); // 파일이 다가올 때 물들기
  const CS = S(1, 420, 14); // 원 크기 (삼키기)
  const UP = S(1, 420, 30); // 화살표
  const PO = S(0, 420, 30); // 원 안의 문서 (원본의 백분율 자리)
  const RO = S(0, 300, 30); // 고리
  const G = S(0, 260, 21); // 초록으로 차기
  const K = S(0, 200, 26); // 체크
  const AF = S(SPIN_ARC, 300, 30); // 고리 길이: 등록되면 한 바퀴로 찬다 (고리와 같은 값)
  const line = (selector: string): Line => ({ el: need<HTMLElement>(selector), cur: null, old: null, o: S(1, 360, 30) });
  const title = line(".file-drop-title");
  const detail = line(".file-drop-detail");
  const springs = [ZS, ZH, CS, UP, PO, RO, G, K, AF, title.o, detail.o];

  let phase: UploadStatus["kind"] = "idle";
  let key = "";
  let near = false;
  let clock = 0;
  let spin = 0;
  let settleAt = Infinity;

  function say(l: Line, text: string) {
    if (l.cur?.textContent === text) return;
    const next = document.createElement("span");
    next.textContent = text;
    l.el.appendChild(next);
    if (!l.cur) {
      l.cur = next; // 처음 글은 굴리지 않는다
      return;
    }
    l.old?.remove();
    l.old = l.cur;
    l.cur = next;
    l.o.x = 0;
    l.o.v = 0;
    l.o.t = 1;
  }

  function show(status: UploadStatus, nearNow: boolean, text: DropText) {
    near = nearNow;
    const next = status.kind === "sending" ? `sending:${status.index}:${status.name}` : status.kind;
    if (next !== key) {
      key = next;
      phase = status.kind;
      if (phase === "sending") {
        CS.x = 1.2;
        ZS.x = 0.965;
        UP.t = 0;
        PO.t = 1;
        RO.t = 1;
        AF.x = AF.t = SPIN_ARC;
        AF.v = 0;
        G.t = 0;
        K.t = 0;
      } else if (phase === "done") {
        PO.t = 0;
        RO.t = 0;
        AF.t = 1;
        G.t = 1;
        K.t = 1;
        CS.x = 0.84;
        settleAt = clock + HOLD;
      } else if (phase === "failed") {
        PO.t = 0;
        RO.t = 0;
        UP.t = 1;
        CS.x = 0.84;
        settleAt = clock + HOLD;
      } else {
        G.t = 0;
        K.t = 0;
        UP.t = 1;
        PO.t = 0;
        RO.t = 0;
        settleAt = Infinity;
      }
    }
    say(title, text.title);
    say(detail, text.detail);
  }

  function frame(dt: number) {
    clock += dt;
    if (phase === "sending") spin += dt;
    ZH.t = phase === "idle" && near ? 1 : 0;
    for (const s of springs) step(s, dt);
    if (clock >= settleAt) {
      settleAt = Infinity;
      onSettled();
    }
  }

  function render() {
    const h = clamp(ZH.x, 0, 1);
    zone.style.setProperty("--h", h.toFixed(3));
    zone.style.transform = `scale(${(ZS.x * (1 + 0.025 * ZH.x)).toFixed(4)})`;
    core.style.transform = `translateY(${(-5 * ZH.x).toFixed(2)}px) scale(${CS.x.toFixed(4)})`;
    const bob = reduce ? 0 : -3.5 * h * (0.5 + 0.5 * Math.sin(clock * 7));
    up.style.opacity = clamp(UP.x, 0, 1).toFixed(3);
    up.style.transform = `translateY(${(bob + (1 - UP.x) * -12).toFixed(2)}px) scale(${(0.6 + 0.4 * UP.x).toFixed(3)})`;
    doc.style.opacity = clamp(PO.x, 0, 1).toFixed(3);
    doc.style.transform = `scale(${(0.7 + 0.3 * PO.x).toFixed(3)})`;
    ring.style.opacity = clamp(RO.x, 0, 1).toFixed(3);
    ring.style.transform = `rotate(${(-90 + spin * SPIN_SPEED).toFixed(1)}deg)`;
    arc.style.strokeDashoffset = (RING * (1 - clamp(AF.x, 0, 1))).toFixed(2);
    flood.style.transform = `scale(${Math.max(0, G.x).toFixed(4)})`;
    ok.style.opacity = clamp(K.x * 4, 0, 1).toFixed(3);
    tick.style.strokeDashoffset = (24 * (1 - clamp(K.x, 0, 1))).toFixed(2);
    for (const l of [title, detail]) {
      if (!l.cur) continue;
      const o = clamp(l.o.x, 0, 1);
      l.cur.style.opacity = clamp((o - 0.35) / 0.65, 0, 1).toFixed(3); // 옛 글이 빠진 뒤에 새 글이 보인다
      l.cur.style.transform = `translateY(${((1 - l.o.x) * 16).toFixed(2)}px)`;
      if (!l.old) continue;
      if (o > 0.985) {
        l.old.remove();
        l.old = null;
      } else {
        l.old.style.opacity = clamp(1 - o * 1.8, 0, 1).toFixed(3);
        l.old.style.transform = `translateY(${(-l.o.x * 16).toFixed(2)}px)`;
      }
    }
  }

  const stopLoop = startLoop(frame, render);

  return {
    show,
    press: () => {
      ZS.x = 0.975;
    },
    stop: () => {
      stopLoop();
      title.el.replaceChildren();
      detail.el.replaceChildren();
    },
  };
}
