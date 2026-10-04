/**
 * 탐색 단축키 (U4): Ctrl(Mac은 Cmd)+Shift+O는 목차 열고 닫기, Ctrl(Cmd)+F는 본문 찾기(브라우저 찾기 대신).
 * 한글 입력 상태에서도 잡히도록 물리 키(`code`)를 본다. Reader가 열려 있는 동안 포커스 위치와 무관하게 받는다.
 */
type KeyInput = Readonly<{ code: string; key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }>;

export function navigationKeyAction(event: KeyInput): "toc" | "find" | null {
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return null;
  if (event.shiftKey && event.code === "KeyO") return "toc";
  if (!event.shiftKey && event.code === "KeyF") return "find";
  return null;
}
