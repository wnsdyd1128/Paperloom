import { describe, expect, it } from "vitest";

import type { Answer } from "../answers/api";
import { finishTurn, onAnswerSaved, onTurnFinished, type RunningTurn, runningTurn, startTurn, updateTurn } from "./runningTurn";

const turn: RunningTurn = { prompt: "질문", quote: [], images: [], text: "", runId: null, session: "s1", fork: null };

describe("runningTurn", () => {
  it("대화 칸이 사라져도 논문마다 만드는 중인 차례가 남아, 돌아온 칸이 이어 본다 (2026-11-08 사용자 보고)", () => {
    startTurn("p1", turn);
    updateTurn("p1", (current) => ({ ...current, runId: "r1" }));
    updateTurn("p1", (current) => ({ ...current, text: current.text + "답의 " }));
    updateTurn("p1", (current) => ({ ...current, text: current.text + "앞부분" }));
    expect(runningTurn("p1")).toEqual({ ...turn, runId: "r1", text: "답의 앞부분" });
    expect(runningTurn("p2")).toBeNull(); // 다른 논문에는 없다
    finishTurn("p1", { kind: "cancelled" });
  });

  it("끝나면 듣는 곳이 결과를 먼저 받고(만드는 중 표시가 아직 있다), 그다음 차례가 사라진다", () => {
    const answer = { answer_id: "a1", session_id: "s1" } as Answer;
    const heard: unknown[] = [];
    const stop = onTurnFinished((paperId, finished, outcome) => heard.push([paperId, finished.prompt, outcome, runningTurn(paperId) !== null]));
    startTurn("p1", turn);
    finishTurn("p1", { kind: "done", answer });
    expect(heard).toEqual([["p1", "질문", { kind: "done", answer }, true]]);
    expect(runningTurn("p1")).toBeNull();

    finishTurn("p1", { kind: "error", message: "두 번" }); // 이미 끝난 차례는 다시 알리지 않는다
    stop();
    startTurn("p1", turn);
    finishTurn("p1", { kind: "cancelled" }); // 그만 들은 곳은 받지 않는다
    expect(heard).toHaveLength(1);
  });

  it("답을 저장한 차례는 다른 탭에도 알린다(답변 화면이 다시 읽는다). 중단·실패는 알리지 않는다", async () => {
    const saved: string[] = [];
    const stop = onAnswerSaved((paperId) => saved.push(paperId));
    startTurn("p1", turn);
    finishTurn("p1", { kind: "cancelled" });
    startTurn("p2", turn);
    finishTurn("p2", { kind: "done", answer: { answer_id: "a2", session_id: "s1" } as Answer });
    await expect.poll(() => saved).toEqual(["p2"]);
    stop();
  });
});
