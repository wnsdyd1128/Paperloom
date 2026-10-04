/**
 * 번역 문장의 원문을 PDF.js text layer에서 찾는다 (2026-10-03 사용자 요청: 번역문에 마우스를 올리면 원문 문장도 강조).
 * 문단 글(서버 추출)과 text layer 글은 공백·줄 끝 하이픈(서버가 이은 sched-ulability)·합자(ﬁ)·대소문자가 다를 수 있어
 * 그것을 빼고 비교한다. 같은 글이 쪽에 여럿이면 문단 전체(near)가 있는 자리부터 찾는다.
 */

export type TextPosition = Readonly<{ node: number; offset: number }>;

const IGNORED = /[\s­‐‑-]/u;

function fold(text: string): string {
  let out = "";
  for (const char of text) {
    for (const folded of char.normalize("NFKC").toLowerCase()) if (!IGNORED.test(folded)) out += folded;
  }
  return out;
}

/**
 * parts는 글 노드들의 글(차례대로). 찾으면 시작·끝(끝은 그 노드 안의 다음 위치) 자리, 못 찾으면 null.
 * 글자는 코드 포인트로 읽는다. 수학 글자(𝐿 U+1D43F)처럼 UTF-16 두 칸인 글자를 반씩 나누면 NFKC로 바뀌지 않아 그 문장을 찾지 못한다.
 */
export function locateText(parts: readonly string[], needle: string, near?: string): Readonly<{ start: TextPosition; end: TextPosition }> | null {
  let text = "";
  const map: (TextPosition & { next: number })[] = []; // text의 UTF-16 칸마다 원래 글자 자리와 그 글자 다음 자리
  parts.forEach((part, node) => {
    for (let offset = 0; offset < part.length; ) {
      const char = String.fromCodePoint(part.codePointAt(offset)!);
      const next = offset + char.length;
      for (const folded of char.normalize("NFKC").toLowerCase()) {
        if (IGNORED.test(folded)) continue;
        text += folded;
        for (let unit = 0; unit < folded.length; unit++) map.push({ node, offset, next });
      }
      offset = next;
    }
  });
  const target = fold(needle);
  if (!target) return null;
  const from = near ? Math.max(0, text.indexOf(fold(near))) : 0;
  let at = text.indexOf(target, from);
  if (at < 0) at = text.indexOf(target);
  if (at < 0) return null;
  const last = map[at + target.length - 1];
  return { start: { node: map[at].node, offset: map[at].offset }, end: { node: last.node, offset: last.next } };
}
