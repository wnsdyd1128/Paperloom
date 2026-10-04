import { describe, expect, it } from "vitest";

import type { Answer } from "../answers/api";
import { conversationTurns, type ForkLink, sessionsOf } from "./sessions";

const answer = (session: string | null, prompt: string, created: string) =>
  ({ session_id: session, prompt, question: prompt, created_at: created }) as Answer;

describe("sessionsOf", () => {
  const answers = [
    answer("s1", "첫 대화의 첫 질문", "2026-10-02T01:00:00Z"),
    answer("s2", "둘째 대화", "2026-10-02T02:00:00Z"),
    answer("s1", "첫 대화의 이어 묻기", "2026-10-02T03:00:00Z"),
    answer(null, "대화 밖", "2026-10-02T04:00:00Z"),
  ];

  it("대화마다 묶어 최근 차례 순으로, 이름은 첫 질문 앞부분이다", () => {
    expect(sessionsOf(answers, new Map())).toEqual([
      { id: "s1", title: "첫 대화의 첫 질문", updated: "2026-10-02T03:00:00Z" },
      { id: "s2", title: "둘째 대화", updated: "2026-10-02T02:00:00Z" },
    ]);
  });

  it("바꾼 이름(또는 원문 위에서 옮겨 온 대화의 제목)이 있으면 그것을 쓴다 (2026-10-02 사용자 요청)", () => {
    expect(sessionsOf(answers, new Map([["s2", "캐시 간섭 정리"]])).map((session) => session.title)).toEqual(["첫 대화의 첫 질문", "캐시 간섭 정리"]);
  });
});

describe("conversationTurns", () => {
  // a: 원래 대화, b: a의 둘째 차례 뒤 갈래, c: b의 첫 차례 뒤 갈래. a는 갈래 뒤에도 이어졌다.
  const turn = (id: string, session: string, created: string) => ({ answer_id: id, session_id: session, created_at: created }) as Answer;
  const answers = [
    turn("a1", "a", "01"),
    turn("a2", "a", "02"),
    turn("b1", "b", "03"),
    turn("a3", "a", "04"),
    turn("c1", "c", "05"),
    turn("b2", "b", "06"),
  ];
  const links = new Map<string, ForkLink>([
    ["b", { parent: "a", at: null }],
    ["c", { parent: "b", at: null }],
  ]);
  const ids = (list: readonly Answer[]) => list.map((answer) => answer.answer_id);

  it("갈래는 갈라질 때까지의 원래 대화 차례를 이어받는다 (2026-10-02 사용자 요청)", () => {
    const b = conversationTurns(answers, "b", links);
    expect([ids(b.inherited), ids(b.own)]).toEqual([["a1", "a2"], ["b1", "b2"]]); // 갈래 뒤의 a3은 아니다
    const c = conversationTurns(answers, "c", links);
    expect([ids(c.inherited), ids(c.own)]).toEqual([["a1", "a2", "b1"], ["c1"]]); // 갈래의 갈래는 거슬러 올라간다
    const a = conversationTurns(answers, "a", links);
    expect([ids(a.inherited), ids(a.own)]).toEqual([[], ["a1", "a2", "a3"]]);
  });

  it("아직 첫 답이 없는 갈래(만드는 중)는 원래 대화의 지금까지를 모두 이어받는다", () => {
    const draft = conversationTurns(answers, null, links, { parent: "b", at: null });
    expect([ids(draft.inherited), ids(draft.own)]).toEqual([["a1", "a2", "b1", "b2"], []]);
    expect(conversationTurns(answers, null, links)).toEqual({ inherited: [], own: [] }); // 새 대화
  });

  it("답에서 갈라진 갈래는 그 답까지만 이어받는다 (2026-10-02 사용자 요청: 답마다 갈래)", () => {
    const draft = conversationTurns(answers, null, links, { parent: "b", at: "a1" }); // b가 이어받은 a1에서 다시 가름
    expect([ids(draft.inherited), ids(draft.own)]).toEqual([["a1"], []]);
    const at = new Map([...links, ["d", { parent: "a", at: "a1" }]]);
    const d = conversationTurns([...answers, turn("d1", "d", "07")], "d", at);
    expect([ids(d.inherited), ids(d.own)]).toEqual([["a1"], ["d1"]]); // 갈래를 만든 때가 아니라 그 답까지
  });
});
