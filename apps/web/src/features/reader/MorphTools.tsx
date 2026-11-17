/**
 * 선택 메뉴의 단추줄 (Motion Studies "Morph Tooltip", 2026-11-16 사용자 요청): 영역 도구줄의 동작 단추와 글 선택 메뉴.
 * 단추는 아이콘(하이라이트 색은 견본)만 두고, 이름과 단축키는 줄 위의 말풍선 하나가 보인다. 말풍선은 단추 사이를 숨지 않고 옮겨 가며 새 이름 너비로 늘었다 줄어든다: 옮겨 가는 쪽
 * 가장자리는 단단한 spring(620/36), 반대쪽은 무른 spring(190/19)이라 늘어나며 건너가고, 꼬리는 따로(300/22) 따라간다.
 * 마우스를 올린 단추 뒤의 강조도 같은 두 spring으로 옮겨 간다. 도구줄을 벗어나면 0.14초 기다렸다 숨는다(틈을 지날 때
 * 깜빡이지 않게). 누른 아이콘은 잠깐 작아졌다 돌아온다(520/16). 원본의 자동 시연(혼자 단추를 돌며 고르기)은 뺐다.
 * 단추 이름은 화면 낭독기용 글로 단추 안에 그대로 둔다(말풍선은 보이는 것만 맡는다).
 */
import { Fragment, useEffect, useRef } from "react";

import { Icon, type IconName } from "../../shared/Icon";
import { clamp, reducedMotion, spring, startLoop, step, tune } from "../../shared/spring";
import type { HighlightColor } from "../annotations/api";

export type MorphTool = Readonly<{
  id: string;
  /** 말풍선에 보일 이름 */
  label: string;
  /** 화면 낭독기 이름. 없으면 label */
  name?: string;
  /** 아이콘. swatch가 있으면 아이콘 대신 그 색 견본을 보인다 */
  icon?: IconName;
  /** 하이라이트 색 견본(색은 --mark-c1…c3) */
  swatch?: HighlightColor;
  /** 아이콘 아래 짧은 밑줄 색(하이라이트 단추의 마지막 색) */
  underline?: string;
  /** 앞 단추와 사이에 구분선 */
  divider?: boolean;
  /** 말풍선에 보일 단축키(예: E, Ctrl+C) */
  shortcut?: string;
  /** aria-keyshortcuts 값(예: E, Control+C) */
  keys?: string;
  primary?: boolean;
  onClick: () => void;
}>;

type Props = Readonly<{
  tools: readonly MorphTool[];
  disabled: boolean;
  /** 메뉴(role=menu) 안이면 단추를 menuitem으로 둔다 */
  itemRole?: "menuitem";
}>;

const LEAD = [620, 36] as const;
const TRAIL = [190, 19] as const;
const HIDE_AFTER = 0.14;

export function MorphTools({ tools, disabled, itemRole }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const motion = useRef<Motion | null>(null);
  useEffect(() => {
    const begun = startMotion(root.current!);
    motion.current = begun;
    return begun.stop;
  }, []);

  return (
    <div ref={root} className="morph-tools" onPointerLeave={() => motion.current?.leave()}>
      <i className="morph-tail" aria-hidden="true" />
      <div className="morph-tip" aria-hidden="true">
        {tools.map((tool) => (
          <span key={tool.id} className="morph-label">
            {tool.label}
            {tool.shortcut && <kbd>{tool.shortcut}</kbd>}
          </span>
        ))}
      </div>
      <i className="morph-hl" aria-hidden="true" />
      {tools.map((tool, index) => (
        <Fragment key={tool.id}>
          {tool.divider && <span className="morph-divider" aria-hidden="true" />}
          <button
            type="button"
            role={itemRole}
            className={["morph-tool", tool.primary && "is-primary", tool.swatch && "is-swatch"].filter(Boolean).join(" ")}
            aria-keyshortcuts={tool.keys}
            disabled={disabled}
            onPointerEnter={() => motion.current?.point(index)}
            onFocus={() => motion.current?.point(index)}
            onBlur={() => motion.current?.leave()}
            onClick={() => {
              motion.current?.press(index);
              tool.onClick();
            }}
          >
            <span className="morph-glyph" aria-hidden="true">
              {tool.swatch ? <span className="morph-swatch" data-color={tool.swatch} /> : tool.icon && <Icon name={tool.icon} size={18} />}
              {tool.underline && <span className="morph-underline" style={{ background: tool.underline }} />}
            </span>
            <span className="sr-only">{tool.name ?? tool.label}</span>
          </button>
        </Fragment>
      ))}
    </div>
  );
}

type Motion = Readonly<{ point: (index: number) => void; leave: () => void; press: (index: number) => void; stop: () => void }>;

function startMotion(root: HTMLElement): Motion {
  const reduce = reducedMotion();
  const S = (x: number, stiffness: number, damping: number) => spring(x, stiffness, damping, reduce);
  const need = <T extends Element>(selector: string) => root.querySelector<T>(selector)!;
  const tip = need<HTMLElement>(".morph-tip");
  const tail = need<HTMLElement>(".morph-tail");
  const hl = need<HTMLElement>(".morph-hl");
  const buttons = [...root.querySelectorAll<HTMLElement>(".morph-tool")];
  const icons = buttons.map((button) => ({ el: button.querySelector<HTMLElement>(".morph-glyph")!, p: S(1, 520, 16) }));
  const labels = [...root.querySelectorAll<HTMLElement>(".morph-label")].map((el) => ({ el, o: S(0, 420, 32), dir: 0 }));

  const TL = S(0, ...LEAD); // 말풍선 왼쪽·오른쪽 가장자리
  const TR = S(0, ...LEAD);
  const TX = S(0, 300, 22); // 꼬리 가운데
  const HL = S(0, ...LEAD); // 강조 왼쪽·오른쪽 가장자리
  const HR = S(0, ...LEAD);
  const A = S(0, 420, 24); // 보이기
  const springs = [TL, TR, TX, HL, HR, A, ...labels.map((label) => label.o), ...icons.map((icon) => icon.p)];
  let current = -1;
  let clock = 0;
  let hideAt = Infinity;

  function place(index: number, snap: boolean) {
    const button = buttons[index];
    const centre = button.offsetLeft + button.offsetWidth / 2;
    const half = labels[index].el.offsetWidth / 2;
    const targets: [typeof TL, number][] = [
      [TL, centre - half],
      [TR, centre + half],
      [TX, centre],
      [HL, button.offsetLeft],
      [HR, button.offsetLeft + button.offsetWidth],
    ];
    for (const [s, value] of targets) {
      s.t = value;
      if (snap) {
        s.x = value;
        s.v = 0;
      }
    }
  }

  function point(index: number) {
    hideAt = Infinity;
    if (index === current) {
      A.t = 1;
      return;
    }
    const dir = current < 0 ? 0 : Math.sign(index - current);
    if (A.x < 0.3) {
      // 아직 보이지 않으면 그 자리에서 나타난다
      place(index, true);
      labels.forEach((label, k) => {
        label.o.x = label.o.t = k === index ? 1 : 0;
        label.o.v = 0;
        label.dir = 0;
      });
    } else {
      // 옮겨 가는 쪽 가장자리가 앞서고(LEAD) 반대쪽이 늦게 따라와(TRAIL) 늘어난다
      const [front, back] = dir >= 0 ? [LEAD, TRAIL] : [TRAIL, LEAD];
      for (const s of [TR, HR]) tune(s, front[0], front[1], reduce);
      for (const s of [TL, HL]) tune(s, back[0], back[1], reduce);
      place(index, false);
      labels.forEach((label, k) => {
        if (k === index) {
          label.dir = dir;
          label.o.t = 1;
        } else if (label.o.t === 1) {
          label.dir = -dir;
          label.o.t = 0;
        }
      });
    }
    current = index;
    A.t = 1;
  }

  function leave() {
    hideAt = clock + HIDE_AFTER;
  }

  function press(index: number) {
    icons[index].p.x = 0.78;
    A.x = Math.min(A.x, 0.9);
  }

  function frame(dt: number) {
    clock += dt;
    if (clock >= hideAt) {
      hideAt = Infinity;
      A.t = 0;
      current = -1;
    }
    for (const s of springs) step(s, dt);
  }

  function render() {
    const a = clamp(A.x, 0, 1.15);
    const shown = clamp(A.x, 0, 1).toFixed(3);
    const left = Math.min(TL.x, TR.x - 30);
    const width = TR.x - left;
    tip.style.width = `${width.toFixed(2)}px`;
    tip.style.opacity = shown;
    tip.style.transform = `translate(${left.toFixed(2)}px,${((1 - a) * 6).toFixed(2)}px) scale(${(0.72 + 0.28 * a).toFixed(4)})`;
    const tailX = clamp(TX.x, left + 10, left + width - 10);
    tail.style.opacity = shown;
    tail.style.transform = `translate(${(tailX - 5).toFixed(2)}px,${((1 - a) * 8).toFixed(2)}px) rotate(45deg) scale(${a.toFixed(3)})`;
    hl.style.opacity = shown;
    hl.style.width = `${Math.max(0, HR.x - HL.x).toFixed(2)}px`;
    hl.style.transform = `translateX(${HL.x.toFixed(2)}px)`;
    for (const label of labels) {
      const o = clamp(label.o.x, 0, 1);
      label.el.style.opacity = o.toFixed(3);
      label.el.style.transform = `translateX(calc(-50% + ${(label.dir * (1 - o) * 14).toFixed(2)}px))`;
      label.el.style.filter = !reduce && o > 0.02 && o < 0.98 ? `blur(${((1 - o) * 3).toFixed(2)}px)` : "none";
    }
    for (const icon of icons) icon.el.style.transform = `scale(${icon.p.x.toFixed(4)})`;
  }

  return { point, leave, press, stop: startLoop(frame, render) };
}
