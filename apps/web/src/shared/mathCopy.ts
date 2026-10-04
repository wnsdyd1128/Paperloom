/**
 * 수식 구분 기호 (U6 설정 "화면 설정 · 수식 구분 기호"): 답·추정 표기를 복사할 때의 형식.
 * - dollar: $…$, $$…$$ (답이 쓰는 그대로)
 * - bracket: \(…\), \[…\]
 * - none: 구분 기호 없이 수식 글만
 * 코드(`…`, ```…```) 안의 $는 수식이 아니다. 닫는 $가 같은 줄에 없으면(값 $5) 그대로다.
 */
export type MathDelimiters = "bracket" | "dollar" | "none";

const CODE = /(```[\s\S]*?```|`[^`\n]*`)/;
const DISPLAY = /\$\$([\s\S]+?)\$\$/g;
const INLINE = /(?<![\\$])\$(?![\s$])([^$\n]+?)(?<!\s)\$/g;

export function formatMathForCopy(markdown: string, delimiters: MathDelimiters): string {
  if (delimiters === "dollar") return markdown;
  return markdown
    .split(CODE)
    .map((part, index) =>
      index % 2 === 1
        ? part
        : part
            .replace(DISPLAY, (_, body: string) => (delimiters === "bracket" ? `\\[${body}\\]` : body))
            .replace(INLINE, (_, body: string) => (delimiters === "bracket" ? `\\(${body}\\)` : body)),
    )
    .join("");
}

// 추정 표기의 토막: 공백으로 나누되 {…} 안의 공백(\frac{a + 1}{b})은 나누지 않는다.
const TOKEN = /(?:\{[^{}]*\}|[^\s{}])+/g;
const EDGES = /^([([]*)(.*?)([,.;:)\]]*)$/;
const NOTATION = /[_^]|\\frac/;

/**
 * 추정 표기(reader/subscripts.ts: 문장 속 첨자 `C_k`·분수 `\frac{…}{…}`)의 수식 토막만 구분 기호로 감싼다.
 * 낱말과 토막 앞뒤의 괄호·문장부호는 밖에 둔다.
 */
export function wrapMath(text: string, delimiters: MathDelimiters): string {
  if (delimiters === "none") return text;
  return text.replace(TOKEN, (token) => {
    const [, lead, core, trail] = EDGES.exec(token)!;
    if (!NOTATION.test(core)) return token;
    return lead + (delimiters === "dollar" ? `$${core}$` : `\\(${core}\\)`) + trail;
  });
}
