import { describe, expect, it } from "vitest";

import { relativeTime } from "./time";

describe("relativeTime", () => {
  const now = new Date(2026, 9, 2, 15, 30); // 2026-10-02 15:30 (이 PC 시간대)
  const at = (...parts: [number, number, number, number, number]) => new Date(...parts).toISOString();

  it("한 시간 안은 분으로, 오늘은 시간으로 보인다", () => {
    expect(relativeTime(at(2026, 9, 2, 15, 29), now)).toBe("1분 전");
    expect(relativeTime(new Date(now.getTime() - 20_000).toISOString(), now)).toBe("방금");
    expect(relativeTime(at(2026, 9, 2, 12, 10), now)).toBe("3시간 전");
  });

  it("어제, 올해의 다른 날, 다른 해를 나눈다", () => {
    expect(relativeTime(at(2026, 9, 1, 23, 50), now)).toBe("어제");
    expect(relativeTime(at(2026, 4, 29, 9, 0), now)).toBe("5월 29일");
    expect(relativeTime(at(2025, 11, 3, 9, 0), now)).toBe("2025. 12. 3.");
  });
});
