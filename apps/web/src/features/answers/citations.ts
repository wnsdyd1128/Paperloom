/**
 * 답변 Markdown remark 플러그인.
 * - remarkCitations: 근거 표기 [근거 1], [근거 2, 3]을 누를 수 있는 링크(#cite-번호)로, 쪽 표기 p.19·pp. 19–20·19쪽을
 *   그 첫 쪽으로 가는 링크(#page-쪽)로 바꾼다. 글(text) 노드만 바꾸므로 코드와 이미 링크인 글은 그대로다.
 *   쪽 번호는 PDF 쪽 순서(1부터)로 본다. 논문의 쪽 라벨(예: 28:20)이 아니다 (docs/UI_PLAN.md A11).
 *   대괄호 번호만([12])은 논문의 참고문헌 번호라 글자 그대로다(2026-10-02 사용자 요청). 이 표기 전에 저장한 답
 *   (근거 표기가 하나도 없는 답, legacy)만 대괄호 번호를 옛 근거 링크(#cite-old-번호)로 바꾼다. 서버가 저장할 때
 *   근거로 읽은 번호만 단추가 된다(AnswerMarkdown).
 * - remarkInlineMathTags: 문장 안 수식의 식 번호 \tag{n}을 (n) 글자로 바꾼다(KaTeX는 문장 안 \tag를 그리지 못한다).
 * - remarkOutsideEvidence: "> [근거 밖] …" 인용문에 표시를 단다. 브리지 시스템 프롬프트가 근거에 없는 내용을 이렇게
 *   쓰게 한다(A10). 모델이 지키지 않으면 평소 인용문으로 보인다.
 */

// [근거 1], [근거 2, 3], [근거 22¶3](논문 본문 근거의 문단, 2026-10-02 사용자 요청), [근거 4¶4–5](문단 범위, 같은 날
// 사용자 확인: 모델이 범위를 써서 표기 통째로 링크가 안 됐다. 범위는 첫 문단으로 간다). 항목마다 번호와 문단(있으면)
const ITEM = String.raw`\d{1,3}(?:\s*¶\s*\d{1,3}(?:\s*[–—~-]\s*\d{1,3})?)?`;
const CITATION = new RegExp(String.raw`\[근거\s*(${ITEM}(?:\s*,\s*(?:근거\s*)?${ITEM})*)\]`, "g");
const CITATION_ITEM = /(\d{1,3})(?:\s*¶\s*(\d{1,3})(?:\s*[–—~-]\s*(\d{1,3}))?)?/g;
const OLD_CITATION = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\](?!\()/g;
const HAS_CITATION = /\[근거\s*\d/;
// p.19, pp. 19–20 (앞이 영문자가 아닐 때), 19쪽·19–20쪽 (앞이 숫자·소수점이 아닐 때). 0쪽은 없다.
const PAGE = /(?<![A-Za-z])pp?\.\s?([1-9]\d{0,3})(?:\s?[–-]\s?\d{1,4})?|(?<![\d.])([1-9]\d{0,3})(?:\s?[–-]\s?\d{1,4})?쪽/g;
const OUTSIDE_MARK = /^\[근거 밖\]\s*/;

type MdNode = { type: string; value?: string; url?: string; children?: MdNode[]; data?: unknown };

export const CITE_PREFIX = "#cite-";
export const OLD_CITE_PREFIX = "#cite-old-";
export const PAGE_PREFIX = "#page-";

type Options = Readonly<{ legacy?: boolean }>;

/** 링크 주소(#cite-22p3)의 근거 번호와 문단. 근거 링크가 아니면 null */
export function citeTarget(href: string): Readonly<{ number: number; paragraph: number | null }> | null {
  const match = /^#cite-(\d+)(?:p(\d+))?$/.exec(href);
  return match ? { number: Number(match[1]), paragraph: match[2] ? Number(match[2]) : null } : null;
}

/** 답의 근거 가운데 그 번호·문단. 그 문단이 없으면(저장할 때 없는 문단이었다 등) 같은 번호의 근거로 대신한다. */
export function findCitation<T extends Readonly<{ number: number; paragraph: number | null }>>(
  citations: readonly T[],
  number: number,
  paragraph: number | null,
): T | undefined {
  return citations.find((item) => item.number === number && item.paragraph === paragraph) ?? citations.find((item) => item.number === number);
}

/** 근거 표기 [근거 n]이 하나도 없는 답. 이 표기 전에 저장했거나 근거를 쓰지 않은 답이다. */
export function isLegacyAnswer(markdown: string): boolean {
  return !HAS_CITATION.test(markdown);
}

/** 글 하나를 글·근거 링크·쪽 링크 노드들로 나눈다. 바꿀 것이 없으면 null. */
export function splitCitations(value: string, { legacy = false }: Options = {}): MdNode[] | null {
  const matches = [
    ...[...value.matchAll(CITATION)].map((match) => ({
      index: match.index,
      length: match[0].length,
      links: [...match[1].matchAll(CITATION_ITEM)].map(([, number, paragraph, end]) =>
        paragraph
          ? link(`${CITE_PREFIX}${number}p${paragraph}`, `근거 ${number}¶${paragraph}${end ? `–${end}` : ""}`)
          : link(`${CITE_PREFIX}${number}`, `근거 ${number}`),
      ),
    })),
    ...(legacy ? [...value.matchAll(OLD_CITATION)] : []).map((match) => ({
      index: match.index,
      length: match[0].length,
      links: match[1].split(",").map((number) => link(`${OLD_CITE_PREFIX}${number.trim()}`, `[${number.trim()}]`)),
    })),
    ...[...value.matchAll(PAGE)].map((match) => ({
      index: match.index,
      length: match[0].length,
      links: [link(`${PAGE_PREFIX}${match[1] ?? match[2]}`, match[0])],
    })),
  ].sort((a, b) => a.index - b.index);
  if (matches.length === 0) return null;
  const parts: MdNode[] = [];
  let last = 0;
  for (const match of matches) {
    if (match.index < last) continue; // 겹치면 앞의 것
    if (match.index > last) parts.push({ type: "text", value: value.slice(last, match.index) });
    parts.push(...match.links);
    last = match.index + match.length;
  }
  if (last < value.length) parts.push({ type: "text", value: value.slice(last) });
  return parts;
}

function link(url: string, text: string): MdNode {
  return { type: "link", url, children: [{ type: "text", value: text }] };
}

function visit(node: MdNode, options: Options): void {
  if (!node.children || node.type === "link" || node.type === "linkReference") return;
  node.children = node.children.flatMap((child) => {
    if (child.type === "text" && child.value) return splitCitations(child.value, options) ?? [child];
    visit(child, options);
    return [child];
  });
}

export function remarkCitations(options: Options = {}) {
  return (tree: MdNode) => visit(tree, options);
}

const MATH_TAG = /\\tag(\*?)\{([^{}]*)\}/g;

/**
 * 문장 안 수식($…$)의 식 번호 \tag{n}을 뒤에 붙인 (n) 글자로 바꾼다. KaTeX는 \tag를 따로 쓴 수식($$…$$)에서만
 * 그리고 문장 안에서는 원문을 빨간 글자로 보인다(2026-10-02 사용자 확인). \tag*{x}는 괄호 없이 x다.
 */
export function remarkInlineMathTags() {
  const untag = (value: string) => value.replace(MATH_TAG, (_, star: string, label: string) => `\\qquad\\text{${star ? label : `(${label})`}}`);
  const visitMath = (node: MdNode): void => {
    if (node.type === "inlineMath" && node.value) {
      node.value = untag(node.value);
      // remark-math는 HTML로 넘길 글을 파싱할 때 data.hChildren에 따로 담는다. rehype-katex는 그것을 그린다.
      const data = node.data as { hChildren?: MdNode[] } | undefined;
      data?.hChildren?.forEach((child) => {
        if (child.type === "text" && child.value) child.value = untag(child.value);
      });
    }
    node.children?.forEach(visitMath);
  };
  return (tree: MdNode) => visitMath(tree);
}

export function remarkOutsideEvidence() {
  const mark = (node: MdNode): void => {
    if (node.type === "blockquote") {
      const first = node.children?.[0]?.children?.[0];
      if (first?.type === "text" && first.value && OUTSIDE_MARK.test(first.value)) {
        first.value = first.value.replace(OUTSIDE_MARK, "");
        node.data = { hProperties: { className: ["outside-evidence"] } };
      }
    }
    node.children?.forEach(mark);
  };
  return (tree: MdNode) => mark(tree);
}
