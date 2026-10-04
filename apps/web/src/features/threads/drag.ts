/** 원문 위 창 끌기 (2026-10-02 사용자 요청: 머리를 끌어 옮기기). 순수 함수만 둔다. */

export type Offset = Readonly<{ x: number; y: number }>;

/**
 * 끌기를 시작할 때의 옮김(start)에 포인터가 움직인 만큼(delta)을 더한 새 옮김. 창의 원래 자리(base, 스크롤 내용 좌표)에
 * 옮김을 더한 왼쪽 위가 스크롤 내용의 왼쪽·위 밖으로 나가지 않게 하고, 오른쪽으로는 머리의 잡을 곳(grip px)이 내용 폭 안에
 * 남게 한다(다시 잡을 수 있다). 아래로는 막지 않는다(스크롤 내용이 늘어난다).
 */
export function dragOffset(
  base: Readonly<{ left: number; top: number }>,
  start: Offset,
  delta: Offset,
  bounds: Readonly<{ width: number; grip: number }>,
): Offset {
  const left = Math.min(Math.max(base.left + start.x + delta.x, 0), Math.max(0, bounds.width - bounds.grip));
  const top = Math.max(base.top + start.y + delta.y, 0);
  return { x: left - base.left, y: top - base.top };
}
