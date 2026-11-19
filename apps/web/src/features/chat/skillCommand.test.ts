import { describe, expect, it } from "vitest";

import type { ChatSkill } from "./api";
import { invokedSkill, matchingSkills, skillPrompt, skillQuery, splitSkill } from "./skillCommand";

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

  it("맨 앞의 `/아는 스킬 `만 칩으로 떼어 내고, 이름 뒤 빈칸 하나만 먹는다", () => {
    expect(splitSkill("/review-paper ", SKILLS)).toEqual({ skill: SKILLS[2], rest: "" });
    expect(splitSkill("/distill-paper 학부생  방법 위주", SKILLS)).toEqual({ skill: SKILLS[0], rest: "학부생  방법 위주" });
    expect(splitSkill("/distill-paper\n학부생", SKILLS)?.rest).toBe("학부생");
    expect(splitSkill("/review-paper", SKILLS)).toBeNull(); // 아직 이름을 치는 중
    expect(splitSkill("/doctor 확인", SKILLS)).toBeNull();
    expect(splitSkill("논문을 /review-paper 해줘", SKILLS)).toBeNull();
  });

  it("칩과 글을 합친 질문은 브리지가 다시 같은 스킬로 읽는다", () => {
    expect(skillPrompt("review-paper", "Q1")).toBe("/review-paper Q1");
    expect(skillPrompt(null, "Q1")).toBe("Q1");
    for (const text of ["", "학부생", "\n두 줄"]) expect(invokedSkill(skillPrompt("distill-paper", text).trim(), SKILLS)?.name).toBe("distill-paper");
  });
});
