/** 사용자 설정 REST 클라이언트 (U6, backend/src/paperloom/preferences). 이 PC의 Core에 한 벌만 둔다(A2). */

import { parseJson } from "../../shared/http";
import type { MathDelimiters } from "../../shared/mathCopy";

export type ChatModelName = "sonnet" | "opus" | "haiku";
export type PromptKey = "system" | "explain" | "translate" | "summary";

export type Preferences = Readonly<{
  answer_language: "ko" | "en";
  default_model: ChatModelName;
  paper_text_chars: 12_000 | 40_000 | 120_000 | 300_000;
  theme: "system" | "light" | "dark";
  font_size: number;
  translation_font_size: number | null;
  math_delimiters: MathDelimiters;
  prompts: Readonly<Record<PromptKey, string>>;
}>;

/** 서버와 같은 기본값. 설정을 받기 전이나 받지 못했을 때 쓴다(사용자 결정 D7: Sonnet). */
export const DEFAULT_PREFERENCES: Preferences = {
  answer_language: "ko",
  default_model: "sonnet",
  paper_text_chars: 120_000,
  theme: "system",
  font_size: 14,
  translation_font_size: null,
  math_delimiters: "dollar",
  prompts: { system: "", explain: "", translate: "", summary: "" },
};

/**
 * 논문 본문 한도의 쪽 수 어림. 쪽당 글자 수는 사용자 논문(한 단, 29쪽, 문맥이 세는 대로 88,190자)의 평균 약 3,000자다
 * (2026-10-03 측정). 두 단 논문은 쪽당 글자가 많아 이 쪽 수의 절반쯤이 들어간다.
 */
export const CHARS_PER_PAGE = 3_000;

export function approxPages(chars: number): number {
  return Math.round(chars / CHARS_PER_PAGE);
}

export async function getPreferences(): Promise<Preferences> {
  return parseJson<Preferences>(await fetch("/api/v1/settings"));
}

/** 모든 값을 보내 바꾼다. */
export async function putPreferences(preferences: Preferences): Promise<Preferences> {
  const response = await fetch("/api/v1/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(preferences),
  });
  return parseJson<Preferences>(response);
}
