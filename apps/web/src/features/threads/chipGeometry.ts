/**
 * 본문 옆 칩의 옮김·연결선 (2026-10-02 사용자 요청). 순수 함수만 둔다. 좌표는 PDF 스크롤 내용 좌표(px)다.
 * 옮긴 만큼은 쪽 너비에 대한 비율로 기억한다: 확대·축소하면 쪽과 함께 커져 같은 자리에 있다.
 */

export type Offset = Readonly<{ x: number; y: number }>;
type Box = Readonly<{ left: number; top: number; right: number; bottom: number }>;
type ChipBox = Readonly<{ left: number; top: number; width: number; height: number }>;

export function toPageUnits(offset: Offset, pageWidth: number): Offset {
  return { x: offset.x / pageWidth, y: offset.y / pageWidth };
}

export function toPixels(units: Offset | undefined, pageWidth: number): Offset {
  return units ? { x: units.x * pageWidth, y: units.y * pageWidth } : { x: 0, y: 0 };
}

/**
 * 고른 곳(그 줄들의 상자)과 칩을 잇는 선. 칩이 가로로 떨어져 있으면 마주 보는 끝의 가운데끼리, 가로로 겹치면 위·아래
 * 가장자리끼리(고른 곳 쪽 끝은 칩 가운데의 가로 위치를 고른 곳 안으로 맞춘다) 잇는다. 칩이 고른 곳 위에 겹쳐 있으면 null.
 */
export function leaderLine(anchor: Box, chip: ChipBox): { x1: number; y1: number; x2: number; y2: number } | null {
  const chipRight = chip.left + chip.width;
  const chipBottom = chip.top + chip.height;
  const anchorMiddle = (anchor.top + anchor.bottom) / 2;
  const chipMiddle = chip.top + chip.height / 2;
  if (chip.left >= anchor.right) return { x1: anchor.right, y1: anchorMiddle, x2: chip.left, y2: chipMiddle };
  if (chipRight <= anchor.left) return { x1: anchor.left, y1: anchorMiddle, x2: chipRight, y2: chipMiddle };
  const chipCenter = chip.left + chip.width / 2;
  const x = Math.min(Math.max(chipCenter, anchor.left), anchor.right);
  if (chip.top >= anchor.bottom) return { x1: x, y1: anchor.bottom, x2: chipCenter, y2: chip.top };
  if (chipBottom <= anchor.top) return { x1: x, y1: anchor.top, x2: chipCenter, y2: chipBottom };
  return null;
}
