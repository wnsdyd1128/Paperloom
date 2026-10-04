import type { TranslatedSentence } from "./api";

/** 번역 한 묶음과 그 원문 범위들(문단 text 안의 [시작, 끝)). 마우스를 올리면 묶음과 원문 범위를 함께 강조한다. */
export type SentenceGroup = Readonly<{ text: string; ranges: readonly (readonly [number, number])[] }>;

/** 빈 번역은 어순 때문에 앞 문장 번역에 합쳐 옮긴 것이므로(브리지 번역 규칙) 그 원문 범위를 앞 묶음에 더한다. */
export function sentenceGroups(sentences: readonly TranslatedSentence[]): SentenceGroup[] {
  const groups: { text: string; ranges: (readonly [number, number])[] }[] = [];
  for (const sentence of sentences) {
    const range = [sentence.start, sentence.end] as const;
    if (sentence.text || groups.length === 0) groups.push({ text: sentence.text, ranges: [range] });
    else groups[groups.length - 1].ranges.push(range);
  }
  return groups;
}
