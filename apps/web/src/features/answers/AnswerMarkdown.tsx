import "katex/dist/katex.min.css";

import Markdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { citeTarget, isLegacyAnswer, OLD_CITE_PREFIX, PAGE_PREFIX, remarkCitations, remarkInlineMathTags, remarkOutsideEvidence } from "./citations";

type Props = Readonly<{
  markdown: string;
  /** 근거 번호(와 문단 ¶)를 누를 수 있는지. 그 번호가 packet에 없으면 false(누를 수 없게 보인다) */
  canCite: (number: number, paragraph: number | null) => boolean;
  onCite: (number: number, paragraph: number | null) => void;
  /** 쪽 표기(p.19·19쪽)를 눌렀을 때. 없으면 쪽 표기는 글자로만 보인다. pageNumber는 1부터다. */
  onPage?: (pageNumber: number) => void;
}>;

/**
 * AI 답변 Markdown을 그린다 (표·목록·코드·수식 $…$). 모델이 쓴 글이므로 안전하게만 그린다:
 * HTML은 해석하지 않고 글자로 보이며(react-markdown 기본), javascript: 같은 링크는 지워지고(기본 urlTransform),
 * 이미지는 외부 주소를 불러오지 않도록 대체 글로만 보인다. 근거 표기 [근거 n]·쪽 표기는 원문 위치로 가는 단추가 되고,
 * "> [근거 밖]" 인용문은 "근거 밖 · 일반 지식" 칸으로 따로 보인다. 논문의 참고문헌 번호 [12]는 글자 그대로다.
 */
export function AnswerMarkdown({ markdown, canCite, onCite, onPage }: Props) {
  const components: Components = {
    a: ({ href, children }) => {
      // 근거 표기 전에 저장한 답의 [n]: 저장할 때 근거로 읽은 번호만 단추로, 나머지는 글자 그대로 둔다.
      if (href?.startsWith(OLD_CITE_PREFIX)) {
        const number = Number(href.slice(OLD_CITE_PREFIX.length));
        return canCite(number, null) ? (
          <button type="button" className="cite-chip" onClick={() => onCite(number, null)} title="원문 위치 보기">
            근거 {number}
          </button>
        ) : (
          <>{children}</>
        );
      }
      const target = href ? citeTarget(href) : null;
      if (target) {
        const { number, paragraph } = target;
        return canCite(number, paragraph) ? (
          <button type="button" className="cite-chip" onClick={() => onCite(number, paragraph)} title="원문 위치 보기">
            {children}
          </button>
        ) : (
          <span className="cite-chip is-missing" title="문맥에 없는 근거 번호">
            {children}
          </span>
        );
      }
      if (href?.startsWith(PAGE_PREFIX)) {
        const pageNumber = Number(href.slice(PAGE_PREFIX.length));
        return onPage ? (
          <button type="button" className="cite-chip is-page" onClick={() => onPage(pageNumber)} title={`${pageNumber}쪽으로 가기`}>
            {children}
          </button>
        ) : (
          <>{children}</>
        );
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      );
    },
    blockquote: ({ className, children }) =>
      className?.includes("outside-evidence") ? (
        <aside className="outside-evidence" aria-label="근거 밖 내용">
          <span className="outside-evidence-label">근거 밖 · 일반 지식</span>
          {children}
        </aside>
      ) : (
        <blockquote>{children}</blockquote>
      ),
    img: ({ alt }) => <span className="muted">[그림: {alt || "설명 없음"}]</span>,
  };
  return (
    <div className="markdown">
      <Markdown
        remarkPlugins={[remarkGfm, remarkMath, remarkInlineMathTags, remarkOutsideEvidence, [remarkCitations, { legacy: isLegacyAnswer(markdown) }]]}
        rehypePlugins={[rehypeKatex]}
        components={components}
      >
        {markdown}
      </Markdown>
    </div>
  );
}
