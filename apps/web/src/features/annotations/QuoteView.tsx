/**
 * 원문 인용과 첨자 추정 표기 (IMPL §5.4). 인용은 추출된 그대로 보이고, 추정 표기는 "추정" 표시와 함께
 * 따로 보인다. 색만으로 구분하지 않도록 글자 표시를 붙인다 (IMPL §10.4).
 */
export function QuoteView({ quote, displayQuote }: { quote: string; displayQuote: string | null }) {
  return (
    <>
      <blockquote className="quote">{quote}</blockquote>
      {displayQuote && (
        <p className="display-quote">
          <span className="badge" title="PDF의 글자 크기와 위치로 첨자를 추정한 표기입니다. 원문 인용은 위와 같습니다.">
            추정
          </span>{" "}
          <code>{displayQuote}</code>
        </p>
      )}
    </>
  );
}
