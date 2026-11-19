import { describe, expect, it } from "vitest";

import type { ChatSkill } from "./api";
import { invokedSkill, matchingSkills, skillQuery } from "./skillCommand";

const skill = (name: string): ChatSkill => ({ name, description: `${name} 설명`, argument_hint: "[인자]", tools: [] });
const SKILLS = [skill("distill-paper"), skill("explore-literature"), skill("review-paper")];

describe("skillCommand", () => {
  it("입력칸이 `/`로 시작하고 빈칸이 없을 때만 이름을 고르는 중이다", () => {
    expect(skillQuery("/")).toBe("");
    expect(skillQuery("/rev")).toBe("rev");
    expect(skillQuery("/review-paper ")).toBeNull(); // 이름을 다 고르고 인자를 쓰는 중
    expect(skillQuery("이 논문 /review")).toBeNull();
    expect(skillQuery("")).toBeNull();
  });

  it("친 이름으로 시작하는 스킬을 먼저 보이고, 이름에 든 것도 보인다", () => {
    expect(matchingSkills(SKILLS, "").map((item) => item.name)).toEqual(["distill-paper", "explore-literature", "review-paper"]);
    expect(matchingSkills(SKILLS, "re").map((item) => item.name)).toEqual(["review-paper", "explore-literature"]);
    expect(matchingSkills(SKILLS, "PAPER").map((item) => item.name)).toEqual(["distill-paper", "review-paper"]);
    expect(matchingSkills(SKILLS, "zzz")).toEqual([]);
  });

  it("질문 맨 앞의 아는 스킬 이름만 스킬 명령이다(브리지와 같은 규칙)", () => {
    expect(invokedSkill("/review-paper Q1", SKILLS)?.name).toBe("review-paper");
    expect(invokedSkill("/distill-paper", SKILLS)?.name).toBe("distill-paper");
    expect(invokedSkill("/distill-paper\n학부생", SKILLS)?.name).toBe("distill-paper");
    expect(invokedSkill("/review-paperX", SKILLS)).toBeNull();
    expect(invokedSkill("/doctor", SKILLS)).toBeNull();
    expect(invokedSkill("논문을 /review-paper", SKILLS)).toBeNull();
  });
});
