import { describe, expect, it } from "vitest";

import type { Anchor } from "../annotations/api";
import type { Answer } from "../answers/api";
import { planTurn, type TurnInput } from "./turnPlan";

const anchor = { anchor_id: "a1" } as Anchor;
const turn = (scope: Answer["scope"], scope_page: number | null = null, packet_id = "k-last") => ({ scope, scope_page, packet_id }) as Answer;
const input = (overrides: Partial<TurnInput>): TurnInput => ({
  question: "q",
  scope: "paper",
  pageIndex: 4,
  versionId: "v1",
  attachments: [],
  turns: [],
  ...overrides,
});

describe("planTurn", () => {
  it("새 대화에서 논문 본문 범위면 본문 packet을 만든다", () => {
    expect(planTurn(input({}))).toEqual({ kind: "new", request: { intent: "ask", question: "q", anchors: [], scope: "paper", version_id: "v1" } });
  });

  it("현재 쪽 범위는 그 쪽 번호를 보낸다", () => {
    expect(planTurn(input({ scope: "page" }))).toEqual({
      kind: "new",
      request: { intent: "ask", question: "q", anchors: [], scope: "page", version_id: "v1", page_index: 4 },
    });
  });

  it("그 대화에 이미 보낸 범위면 질문만 이어 보낸다", () => {
    expect(planTurn(input({ turns: [turn("paper", null, "k1"), turn("selection")] }))).toEqual({ kind: "reuse", packetId: "k-last" });
    expect(planTurn(input({ scope: "page", turns: [turn("page", 4)] }))).toEqual({ kind: "reuse", packetId: "k-last" });
  });

  it("다른 쪽을 보고 있으면 그 쪽 본문을 새로 보낸다", () => {
    expect(planTurn(input({ scope: "page", turns: [turn("page", 3)] }))).toMatchObject({ kind: "new", request: { scope: "page", page_index: 4 } });
  });

  it("붙인 위치가 있으면 새 packet이고, 범위 본문은 아직 안 보냈을 때만 함께 보낸다", () => {
    const anchors = [{ anchor_id: "a1", include_context: true, include_image: true }];
    expect(planTurn(input({ attachments: [anchor] }))).toEqual({
      kind: "new",
      request: { intent: "ask", question: "q", anchors, scope: "paper", version_id: "v1" },
    });
    expect(planTurn(input({ attachments: [anchor], turns: [turn("paper")] }))).toEqual({
      kind: "new",
      request: { intent: "ask", question: "q", anchors, scope: "selection" },
    });
  });

  it("예전 packet(범위 없음)은 본문을 보냈다고 보지 않는다", () => {
    expect(planTurn(input({ turns: [turn(null)] }))).toMatchObject({ kind: "new", request: { scope: "paper" } });
  });

  it("요약은 요약 요청으로 보낸다", () => {
    expect(planTurn(input({ intent: "summarize" }))).toMatchObject({ kind: "new", request: { intent: "summarize", scope: "paper" } });
  });
});
