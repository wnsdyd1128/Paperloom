/**
 * 원문 탭(Reader)과 사이드바에서 분리한 대화 탭 사이의 소식 (2026-11-09 사용자 요청: 대화를 분리하는 단추).
 * 번역 탭(translation/channel.ts)처럼 BroadcastChannel을 쓰고, 대화가 논문마다 이어지므로 논문마다 한 채널이다.
 * 원문 탭은 지금 버전·쪽과 대화 목록에서 뺄 대화(원문 위 대화)를 알리고, 고른 위치·요약 같은 일을 맡긴다.
 * 대화 탭은 근거·위치·쪽을 원문 탭에 보이게 하고, 답을 버리거나 대화 이름을 바꾸거나 지운 것을 알린다.
 * 대화 탭이 열려 있는 동안 원문 탭의 사이드바 대화는 쉬고, 대화 탭이 닫히면 사이드바로 돌아온다.
 */
import type { Answer, Citation } from "../answers/api";
import type { ChatRequest } from "./ChatPanel";

/** 원문 탭 하나의 지금 상태. 원문 탭이 여럿이면 마지막에 알린 탭을 따른다 */
export type ReaderState = Readonly<{ readerId: string; versionId: string; pageIndex: number; hiddenSessions: readonly string[] }>;

export type ChatTabMessage =
  | Readonly<{ type: "hello" }> // 대화 탭 → 원문 탭: 열렸다. 원문 탭이 지금 상태와 맡겨 둔 일을 보낸다
  | Readonly<{ type: "chat-open" }> // 대화 탭 → 원문 탭: 대화 탭이 열려 있다(새로 연 원문 탭에 답한다)
  | Readonly<{ type: "chat-gone" }> // 대화 탭 → 원문 탭: 닫혔다. 사이드바 대화로 돌아간다
  | Readonly<{ type: "reader"; state: ReaderState }> // 원문 탭 → 대화 탭: 열렸거나 쪽·버전·뺄 대화가 바뀌었다
  | Readonly<{ type: "reader-gone"; readerId: string }> // 원문 탭이 닫히거나 다른 화면으로 갔다
  | Readonly<{ type: "request"; request: ChatRequest }> // 원문 탭 → 대화 탭: 맡기는 일(위치 붙이기·대화 열기·요약)
  | Readonly<{ type: "close" }> // 원문 탭 → 대화 탭: 사이드바로 되돌린다. 대화 탭은 스스로 닫는다
  | Readonly<{ type: "ping" }> // 원문 탭 → 대화 탭: 아직 열려 있는지 묻는다. 대화 탭은 "chat-open"으로 답한다
  | Readonly<{ type: "show-citation"; citation: Citation }> // 대화 탭 → 원문 탭부터 아래는 모두 이쪽이다
  | Readonly<{ type: "show-anchor"; anchorId: string }>
  | Readonly<{ type: "show-page"; pageNumber: number }>
  | Readonly<{ type: "discarded"; answer: Answer }>
  | Readonly<{ type: "renamed"; sessionId: string; title: string }>
  | Readonly<{ type: "deleted"; sessionId: string }>;

export type ChatChannel = Readonly<{ post: (message: ChatTabMessage) => void; close: () => void }>;

export function openChatChannel(paperId: string, onMessage: (message: ChatTabMessage) => void): ChatChannel {
  if (typeof BroadcastChannel === "undefined") return { post: () => undefined, close: () => undefined };
  const channel = new BroadcastChannel(`paperloom-chat:${paperId}`);
  channel.onmessage = (event: MessageEvent<ChatTabMessage>) => onMessage(event.data);
  return { post: (message) => channel.postMessage(message), close: () => channel.close() };
}

/**
 * 그 논문의 대화 탭을 열거나, 이미 열려 있으면 앞으로 가져온다. 열린 탭은 다시 불러오지 않는다(답을 만드는 중일 수 있다).
 * 사용자가 누른 동안에 불러야 한다. 아니면 브라우저가 새 탭을 막는다.
 * 새로 열었으면 true, 열려 있던 탭이면 false, 막혔으면 null이다.
 */
export function showChatTab(paperId: string, url: string): boolean | null {
  const tab = window.open("", `paperloom-chat-${paperId}`);
  if (!tab) return null;
  let fresh = false;
  try {
    fresh = tab.location.href === "about:blank";
  } catch {
    // 같은 이름의 창이 다른 사이트를 열고 있으면 읽지 못한다. 그 창은 그대로 둔다
  }
  if (fresh) tab.location.replace(url);
  tab.focus();
  return fresh;
}
