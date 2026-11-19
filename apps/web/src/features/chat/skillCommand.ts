/**
 * 대화창의 `/` 스킬 명령 (2026-11-19 사용자 결정 "B+C"). 순수 함수다.
 * 질문 맨 앞의 `/이름 인자`가 브리지가 아는 Paperloom 스킬이면 브리지가 그 스킬로 실행한다
 * (backend/src/paperloom/integrations/claude_code/skills.py). 입력칸이 `/`로 시작하고 아직 빈칸이 없으면 이름을 고르는 중이다.
 */

import type { ChatSkill } from "./api";

/** 이름을 고르는 중이면 지금까지 친 이름(`/` 뒤, 빈 글일 수 있다), 아니면 null */
export function skillQuery(text: string): string | null {
  const match = /^\/(\S*)$/.exec(text);
  return match ? match[1] : null;
}

/** 친 이름으로 시작하는 스킬을 먼저, 그다음 이름에 그 글이 든 스킬 */
export function matchingSkills(skills: readonly ChatSkill[], query: string): readonly ChatSkill[] {
  const typed = query.toLowerCase();
  const starts = skills.filter((skill) => skill.name.startsWith(typed));
  return [...starts, ...skills.filter((skill) => !starts.includes(skill) && skill.name.includes(typed))];
}

/** 질문 맨 앞에 쓴 스킬(이름 뒤는 빈칸이나 끝). 브리지의 skills.invoked와 같은 규칙이다 */
export function invokedSkill(text: string, skills: readonly ChatSkill[]): ChatSkill | null {
  const name = /^\/([a-z0-9][a-z0-9-]*)(?=\s|$)/.exec(text)?.[1];
  return skills.find((skill) => skill.name === name) ?? null;
}

/**
 * 입력칸 글 맨 앞의 `/스킬 `(이름 뒤 빈칸 하나까지)을 칩으로 떼어 낸다. 아는 스킬이 아니거나 이름 뒤에 빈칸이 아직 없으면
 * null이다(이름을 치는 중). 고르기·붙여 넣기·돌려 둔 질문이 모두 이 규칙으로 칩이 된다.
 */
export function splitSkill(text: string, skills: readonly ChatSkill[]): Readonly<{ skill: ChatSkill; rest: string }> | null {
  const match = /^\/([a-z0-9][a-z0-9-]*)\s/.exec(text);
  const skill = match ? skills.find((item) => item.name === match[1]) : undefined;
  return match && skill ? { skill, rest: text.slice(match[0].length) } : null;
}

/** 칩과 입력칸 글을 브리지에 보낼 질문으로 합친다(브리지는 맨 앞의 `/이름`을 스킬로 읽는다) */
export function skillPrompt(skill: string | null, text: string): string {
  return skill ? `/${skill} ${text}` : text;
}
