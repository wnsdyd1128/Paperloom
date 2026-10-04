/**
 * Reader 확대 규칙 (IMPL §10.5). 배율은 PDF.js scale 값이다(1 = 100%).
 */

/** 툴바 선택과 Ctrl+± 단계. 브라우저 자체 확대와 같은 단계라 익숙하다. */
export const ZOOM_PRESETS: readonly number[] = [
  0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4, 5,
];
export const MIN_ZOOM = ZOOM_PRESETS[0];
export const MAX_ZOOM = ZOOM_PRESETS[ZOOM_PRESETS.length - 1];
export const DEFAULT_ZOOM = 1;

// 휠 한 칸(Chromium 기준 deltaY 100 px)마다 1.2배. 줄 단위 휠(Firefox)은 한 칸이 3줄이다.
// 트랙패드 핀치도 Ctrl이 켜진 픽셀 단위 휠로 오며 같은 비율을 쓴다.
const WHEEL_NOTCH_FACTOR = 1.2;
const WHEEL_NOTCH_PX = 100;
const DELTA_PX = [1, WHEEL_NOTCH_PX / 3, WHEEL_NOTCH_PX]; // WheelEvent.deltaMode: 픽셀, 줄, 쪽

/**
 * 배율을 허용 범위로 자르고 소수 넷째 자리로 맞춘다. 휠로 확대했다가 같은 칸만큼 축소하면
 * 부동소수 오차 없이 원래 값(예: 1)으로 돌아와 preset과 같아진다.
 */
export function normalizeZoom(scale: number): number {
  return Math.round(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, scale)) * 1e4) / 1e4;
}

/** 현재 배율에서 한 단계 위(1) 또는 아래(-1)의 preset. 범위 끝에서는 끝 값에 머문다. */
export function stepZoom(scale: number, direction: 1 | -1): number {
  // 휠로 만든 값이 preset과 0.1% 안이면 그 preset에 있는 것으로 본다 (99.99%에서 + → 110%).
  const tolerance = 1e-3;
  return direction > 0
    ? (ZOOM_PRESETS.find((preset) => preset > scale * (1 + tolerance)) ?? MAX_ZOOM)
    : (ZOOM_PRESETS.findLast((preset) => preset < scale * (1 - tolerance)) ?? MIN_ZOOM);
}

/** Ctrl+휠 한 번이 요구하는 배율 변화(곱). 위로 굴리면(deltaY < 0) 확대한다. */
export function wheelZoomFactor(deltaY: number, deltaMode: number): number {
  const px = deltaY * (DELTA_PX[deltaMode] ?? 1);
  return WHEEL_NOTCH_FACTOR ** (-px / WHEEL_NOTCH_PX);
}

export type ZoomKeyAction = "in" | "out" | "reset";

type KeyInput = Readonly<{ key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean }>;

/** Ctrl(macOS는 Cmd) + `+`·`=`·`-`·`0`이 뜻하는 확대 조작. 해당하지 않으면 null. */
export function zoomKeyAction(event: KeyInput): ZoomKeyAction | null {
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return null;
  switch (event.key) {
    case "+":
    case "=":
      return "in";
    case "-":
      return "out";
    case "0":
      return "reset";
    default:
      return null;
  }
}

export function formatZoom(scale: number): string {
  return `${Math.round(scale * 100)}%`;
}

type Pin = Readonly<{ page: HTMLElement; fx: number; fy: number; clientX: number; clientY: number }>;

/**
 * Ctrl+휠 확대에서 커서 아래의 PDF 지점을 같은 화면 좌표에 남긴다. `pin(x, y)`를 확대 직전에 부르고,
 * 돌려받은 함수를 확대 직후에 불러 스크롤을 맞춘다. 좌표가 페이지 사이 여백이면 세로로 가장 가까운
 * 페이지를 기준으로 삼는다. 스크롤할 수 있는 범위 밖(예: 페이지 왼쪽 여백 근처에서 확대)은 맞추지 못한다.
 *
 * 같은 커서 위치에서 이어지는 휠(핀치 등)은 처음 잡은 지점을 계속 쓴다. 이벤트마다 새로 잡으면 스크롤
 * 위치의 정수 반올림 오차(이벤트마다 축별 최대 0.5 px)가 쌓여 지점이 밀린다. 커서가 움직였거나 그사이
 * 스크롤했으면 새로 잡는다.
 *
 * PDF.js의 updateScale({ origin })은 쓰지 않는다. 배율을 0.01로, 기준 위치를 정수 PDF 좌표로
 * 반올림해 핀치처럼 작은 변화가 이어지면 배율이 바뀌지 않거나 지점이 밀린다.
 */
export function createZoomPinner(container: HTMLElement, pageSelector = ".page") {
  let last: Pin | null = null;
  let scrollAfterLast: readonly [number, number] | null = null;

  function capture(clientX: number, clientY: number): Pin | null {
    let page: HTMLElement | null = null;
    let distance = Infinity;
    for (const candidate of container.querySelectorAll<HTMLElement>(pageSelector)) {
      const rect = candidate.getBoundingClientRect();
      const candidateDistance = Math.max(rect.top - clientY, clientY - rect.bottom, 0);
      if (candidateDistance < distance) [page, distance] = [candidate, candidateDistance];
    }
    if (!page) return null;
    const rect = page.getBoundingClientRect();
    return { page, fx: (clientX - rect.left) / rect.width, fy: (clientY - rect.top) / rect.height, clientX, clientY };
  }

  return {
    pin(clientX: number, clientY: number): () => void {
      const continuing =
        last?.clientX === clientX &&
        last.clientY === clientY &&
        scrollAfterLast?.[0] === container.scrollLeft &&
        scrollAfterLast[1] === container.scrollTop;
      const pin = continuing ? last : capture(clientX, clientY);
      last = pin;
      return () => {
        if (!pin) return;
        const rect = pin.page.getBoundingClientRect();
        container.scrollLeft += rect.left + pin.fx * rect.width - pin.clientX;
        container.scrollTop += rect.top + pin.fy * rect.height - pin.clientY;
        scrollAfterLast = [container.scrollLeft, container.scrollTop];
      };
    },
  };
}
