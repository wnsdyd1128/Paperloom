/**
 * 선택한 그림·영역을 이미지로 클립보드에 복사한다 (Ctrl/Cmd+C, 패널 버튼).
 *
 * 이미지는 서버가 영역 이미지와 같은 렌더러로 그린다(화면에 보이는 방향, PDF 1 pt당 2 px). 클립보드 API는
 * 보안 출처(127.0.0.1·localhost·https)에서만 쓸 수 있다.
 */
import type { Box } from "./geometry";

export const COPY_SCALE = 2;

export class ClipboardUnavailable extends Error {}

export function pageRegionImageUrl(versionId: string, pageIndex: number, box: Box, scale = COPY_SCALE): string {
  const values = [box.u0, box.v0, box.u1, box.v1].join(",");
  const id = encodeURIComponent(versionId);
  return `/api/v1/versions/${id}/pages/${pageIndex}/image?box=${encodeURIComponent(values)}&scale=${scale}`;
}

type KeyInput = Readonly<{ code: string; key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }>;

/** Ctrl(macOS는 Cmd)+C. 한글 입력 상태에서는 key가 "ㅊ"이므로 물리 키(code)를 본다. */
export function isCopyShortcut(event: KeyInput): boolean {
  if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return false;
  return event.code === "KeyC" || event.key.toLowerCase() === "c";
}

/**
 * 이미지 주소의 PNG를 클립보드에 쓴다. 클립보드 쓰기는 키를 누른 순간(사용자 동작 안)에 시작해야 하므로
 * 내려받기를 기다리지 않고 PNG를 Promise로 넘긴다.
 */
export async function copyImageToClipboard(url: string): Promise<void> {
  if (!window.isSecureContext || !navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
    throw new ClipboardUnavailable();
  }
  const png = fetch(url).then(async (response) => {
    if (!response.ok) throw new Error(`영역 이미지 ${response.status}`);
    return response.blob();
  });
  await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
}

/** 포커스가 글을 쓰는 칸에 있으면 Ctrl+C는 그 글을 복사해야 한다. */
export function isEditable(element: Element | null): boolean {
  return (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement ||
    (element instanceof HTMLElement && element.isContentEditable)
  );
}
