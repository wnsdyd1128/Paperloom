/**
 * 원문 탭과 별도 번역 탭 사이의 소식 (U7, 시안 Translation Tab). 같은 버전끼리 BroadcastChannel로 쪽 이동을 맞추고,
 * 번역 탭에서 문장에 마우스를 올리면 원문 탭이 그 원문 문장을 강조한다.
 * 레이아웃 유지 번역 탭과는 쪽 안 자리(scroll)까지 맞춘다: 두 창을 나란히 두면 같은 쪽의 같은 자리가 위끝에 온다(2026-10-04
 * 사용자 확인: 쪽 번호만 맞춰 쪽 위치가 어긋났다). 받은 쪽은 그 자리로 옮긴 스크롤을 되돌려 보내지 않는다.
 */
import type { LinkedSentence } from "./linkedSentence";
import type { PageInfo } from "./schedule";
import type { SourceHover } from "./TranslatedPage";

export type TranslationMessage =
  | Readonly<{ type: "page"; pageIndex: number }> // 쪽을 옮겼다(양쪽). 글로 읽기 번역 탭이 쓴다
  | Readonly<{ type: "scroll"; pageIndex: number; offset: number }> // 위끝이 그 쪽의 offset(쪽 높이 비율) 자리다(원문 탭·레이아웃 유지 번역 탭)
  | Readonly<{ type: "hover"; hover: SourceHover }> // 번역 탭 → 원문 탭
  | Readonly<{ type: "linked"; linked: LinkedSentence }> // 원문 탭 → 번역 탭: 원문 문장에 마우스를 올린 동안 강조할 번역 문장
  | Readonly<{ type: "translated"; pageIndex: number }> // 번역 탭 → 원문 탭: 그 쪽 번역이 있다(원문 탭이 다시 읽어 원문 → 번역 강조에 쓴다)
  | Readonly<{ type: "hello" }>; // 번역 탭이 열렸다 → 원문 탭이 지금 쪽을 보낸다

export type TranslationChannel = Readonly<{ post: (message: TranslationMessage) => void; close: () => void }>;

export function openTranslationChannel(versionId: string, onMessage: (message: TranslationMessage) => void): TranslationChannel {
  if (typeof BroadcastChannel === "undefined") return { post: () => undefined, close: () => undefined };
  const channel = new BroadcastChannel(`paperloom-translation:${versionId}`);
  channel.onmessage = (event: MessageEvent<TranslationMessage>) => onMessage(event.data);
  return { post: (message) => channel.postMessage(message), close: () => channel.close() };
}

export type PageFrame = Readonly<{ top: number; height: number }>;

/** 보이는 영역 위끝(viewTop)이 걸친 쪽(frames 차례)과 그 쪽 안 자리(쪽 높이 비율. 첫 쪽 위 여백은 0보다 작고, 쪽 사이 틈은 1 너머) */
export function viewPosition(viewTop: number, frames: readonly PageFrame[]): { pageIndex: number; offset: number } {
  let pageIndex = 0;
  frames.forEach((frame, index) => {
    if (frame.top <= viewTop) pageIndex = index;
  });
  const frame = frames[pageIndex];
  return { pageIndex, offset: frame ? Math.round(((viewTop - frame.top) / frame.height) * 1e6) / 1e6 : 0 };
}

/** 그 쪽(frame)의 offset 자리를 보이는 영역 위끝(viewTop)에 두려면 scrollTop에 더할 값 */
export function scrollDelta(viewTop: number, frame: PageFrame, offset: number): number {
  return frame.top + offset * frame.height - viewTop;
}

/** 쪽 추출 상태(listPageTexts)에서 번역 차례에 쓰는 쪽 정보. 본문이 없는 쪽(no_body_text: 참고문헌·그림·표뿐)은 건너뛴다. */
export function pageInfos(pages: readonly Readonly<{ page_index: number; text_status: string; flags: readonly string[] }>[]): PageInfo[] {
  return pages.map((page) => ({
    pageIndex: page.page_index,
    hasText: (page.text_status === "usable" || page.text_status === "partial") && !page.flags.includes("no_text") && !page.flags.includes("no_body_text"),
  }));
}
