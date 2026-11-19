/**
 * 대화 입력칸 앞의 스킬 칩 (2026-11-19 사용자 요청: 고른 스킬 이름이 질문 글과 구분되게).
 * Motion Studies "Tag input"(designbookmark.com/motion#db-tag-input, tag-input/tags.js)의 칩 움직임을 옮겼다. 생길 때는
 * 이름 폭까지 펴지며 작은 크기에서 튀어나오고, 뺄 때는 폭이 줄고 흐려지며 입력칸이 제자리로 미끄러진다.
 * spring 값은 원본 tags.js 그대로다. 원본의 자동 입력 시연은 실제 입력과 헷갈리므로 뺐다.
 */
import { useLayoutEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";
import { clamp, reducedMotion, type Spring, spring, startLoop, step } from "../../shared/spring";

/** 원본 tags.js의 (stiffness, damping): 폭, 크기, 투명도 */
const WIDTH = [340, 26] as const;
const SCALE = [420, 16] as const;
const OPACITY = [300, 26] as const;
/** 뺀 칩을 지우기까지(초, 원본 0.45) */
const LEAVE = 0.45;
/** 칩 왼쪽 여백과 입력칸까지 간격(.chat-skill-chip margin-left + .chat-input-row gap). 빠지는 동안 이만큼 당긴다 */
const PULL = 4 + 6;

type Motion = { w: Spring; s: Spring; o: Spring; full: number };

type Props = Readonly<{
  /** 고른 스킬 이름. null이 되면 칩이 줄어들며 사라진다 */
  name: string | null;
  onRemove: () => void;
}>;

export function SkillChip({ name, onRemove }: Props) {
  const [shown, setShown] = useState(name); // 그리는 이름. 빠지는 동안은 name이 null이어도 남아 있다
  if (name !== null && name !== shown) setShown(name);
  const chipRef = useRef<HTMLSpanElement>(null);
  const innerRef = useRef<HTMLSpanElement>(null);
  const motion = useRef<Motion | null>(null);

  useLayoutEffect(() => {
    const chip = chipRef.current;
    const inner = innerRef.current;
    if (!chip || !inner) return;
    const reduce = reducedMotion();
    const leaving = name === null;
    const before = motion.current; // 빠지는 중에 다시 고르면 그 자리에서 되돌아온다
    if (!leaving || !before) {
      const full = inner.offsetWidth;
      motion.current = {
        full,
        w: spring(before?.w.x ?? 0, ...WIDTH, reduce),
        s: spring(before?.s.x ?? 0.5, ...SCALE, reduce),
        o: spring(before?.o.x ?? 0, ...OPACITY, reduce),
      };
    }
    const m = motion.current!;
    m.w.t = leaving ? 0 : m.full;
    m.s.t = leaving ? 0.6 : 1;
    m.o.t = leaving ? 0 : 1;
    let left = LEAVE;
    const paint = () => {
      chip.style.width = `${Math.max(0, m.w.x).toFixed(2)}px`;
      chip.style.marginRight = leaving ? `${(-PULL * (1 - clamp(m.w.x / m.full, 0, 1))).toFixed(2)}px` : "";
      chip.style.opacity = clamp(m.o.x, 0, 1).toFixed(3);
      chip.style.transform = `scale(${m.s.x.toFixed(4)})`;
    };
    paint(); // 처음 그리는 화면부터 접힌 칩이다(펼친 칩이 한 번 비치지 않게)
    return startLoop(
      (dt) => {
        step(m.w, dt);
        step(m.s, dt);
        step(m.o, dt);
        if (leaving) left -= dt;
      },
      () => {
        paint();
        if (leaving && left <= 0) {
          motion.current = null;
          setShown(null);
        }
      },
    );
  }, [name, shown]);

  if (shown === null) return null;
  return (
    <span ref={chipRef} className="chat-skill-chip">
      <span ref={innerRef} className="chat-skill-chip-in">
        <span>/{shown}</span>
        <button
          type="button"
          aria-label={`${shown} 스킬 빼기`}
          title="스킬 빼기"
          disabled={name === null}
          onMouseDown={(event) => event.preventDefault()} // 입력칸 포커스를 잃지 않게
          onClick={onRemove}
        >
          <Icon name="x" size={12} />
        </button>
      </span>
    </span>
  );
}
