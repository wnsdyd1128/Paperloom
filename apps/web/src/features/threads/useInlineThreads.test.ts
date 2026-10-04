import { describe, expect, it } from "vitest";

import type { Anchor } from "../annotations/api";
import type { Answer } from "../answers/api";
import type { Thread } from "./api";
import { anchorTitle, answerCount, firstHeading, firstPacketRequest, type InlineThread, lastAnswerAt, withoutAnswer } from "./useInlineThreads";

const anchor = (overrides: Partial<Anchor>): Anchor =>
  ({ kind: "text", page_index: 19, quote: "CITTA is able to partition", display_quote: null, ...overrides }) as Anchor;

describe("firstHeading", () => {
  it("답의 첫 소제목을 강조 기호 없이 쓴다", () => {
    expect(firstHeading("본문\n\n## **U_tot = 3.9**의 의미\n\n설명")).toBe("U_tot = 3.9의 의미");
  });

  it("소제목이 없으면 null", () => {
    expect(firstHeading("소제목 없는 답 # 이건 줄 처음이 아니다")).toBeNull();
  });
});

describe("firstPacketRequest", () => {
  const chosen = anchor({ anchor_id: "a1", version_id: "v1" }); // 20쪽(page_index 19)
  const anchors = [{ anchor_id: "a1", include_context: true, include_image: true }];

  it("설명·질문은 앞쪽부터 고른 쪽 다음 쪽까지와 참고문헌 쪽을 보낸다 (2026-10-04 사용자 요청: 18쪽이면 1–18쪽 + 19쪽)", () => {
    // 마지막 쪽을 고르면 서버가 문서 끝까지로 줄인다(until_page)
    const scope = { scope: "until_page", version_id: "v1", page_index: 20 };
    expect(firstPacketRequest("explain", chosen, "설명")).toEqual({ intent: "explain", question: "설명", anchors, ...scope });
    expect(firstPacketRequest("ask", chosen, "왜?")).toEqual({ intent: "ask", question: "왜?", anchors, ...scope });
  });

  it("번역은 고른 글과 앞뒤 문단만 보낸다", () => {
    expect(firstPacketRequest("translate", chosen, "번역")).toEqual({ intent: "translate", question: "번역", anchors });
  });
});

describe("anchorTitle", () => {
  it("글은 추정 표기가 있으면 그것을, 영역은 종류와 쪽을 쓴다", () => {
    expect(anchorTitle(anchor({ display_quote: "C_{i} ≤ T_{i}" }))).toBe("C_{i} ≤ T_{i}");
    expect(anchorTitle(anchor({ kind: "equation", quote: "" }))).toBe("수식 · 20쪽");
  });
});

describe("answerCount · lastAnswerAt", () => {
  const thread = { answer_count: 1, last_answer_at: "2026-10-02T01:00:00Z", created_at: "2026-10-02T00:59:00Z" } as Thread;
  const item = (answers: readonly Answer[] | null): InlineThread =>
    ({ key: "k", kind: "explain", anchor: anchor({}), title: "t", thread, packet: null, answers, pending: null, error: null }) as InlineThread;

  it("이 화면에서 이어 물은 차례가 있으면 그것을 센다", () => {
    const answers = [{ created_at: "2026-10-02T01:00:00Z" }, { created_at: "2026-10-02T01:05:00Z" }] as Answer[];
    expect(answerCount(item(answers))).toBe(2);
    expect(lastAnswerAt(item(answers))).toBe("2026-10-02T01:05:00Z");
  });

  it("아직 차례를 불러오지 않았으면 서버 기록을 쓴다", () => {
    expect(answerCount(item(null))).toBe(1);
    expect(lastAnswerAt(item(null))).toBe("2026-10-02T01:00:00Z");
  });
});

describe("withoutAnswer", () => {
  const thread = (session: string, count: number) => ({ session_id: session, answer_count: count }) as Thread;
  const item = (key: string, sessionThread: Thread, answers: readonly Answer[] | null): InlineThread =>
    ({ key, kind: "explain", anchor: anchor({}), title: "t", thread: sessionThread, packet: null, answers, pending: null, error: null }) as InlineThread;
  const answer = (id: string, session: string) => ({ answer_id: id, session_id: session }) as Answer;

  it("다른 곳(사이드바 대화)에서 버린 답을 빼고, 답이 남지 않은 대화는 목록에서 뺀다 (2026-10-02 사용자 확인)", () => {
    const items = [
      item("a", thread("s1", 1), null), // 불러오지 않은 대화: 서버 개수로 센다
      item("b", thread("s2", 2), [answer("x", "s2"), answer("y", "s2")]),
      item("c", thread("s3", 1), null),
    ];
    expect(withoutAnswer(items, answer("q", "s1")).map((next) => next.key)).toEqual(["b", "c"]);
    const [b] = withoutAnswer(items, answer("x", "s2")).filter((next) => next.key === "b");
    expect(b.answers?.map((next) => next.answer_id)).toEqual(["y"]);
    expect(withoutAnswer(items, answer("z", "other"))).toBe(items); // 그 대화가 없으면 그대로
  });
});
