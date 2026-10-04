import { describe, expect, it } from "vitest";

import { formatMathForCopy, wrapMath } from "./mathCopy";

describe("formatMathForCopy (U6 수식 구분 기호)", () => {
  const markdown = "문장 안 $C_i \\le T_i$와 따로 쓴 식\n\n$$U = \\sum_i C_i / T_i$$\n\n값은 $5 이다.";

  it("dollar는 그대로", () => {
    expect(formatMathForCopy(markdown, "dollar")).toBe(markdown);
  });

  it("bracket은 \\( \\)와 \\[ \\]", () => {
    expect(formatMathForCopy(markdown, "bracket")).toBe(
      "문장 안 \\(C_i \\le T_i\\)와 따로 쓴 식\n\n\\[U = \\sum_i C_i / T_i\\]\n\n값은 $5 이다.",
    );
  });

  it("none은 구분 기호를 뺀다", () => {
    expect(formatMathForCopy(markdown, "none")).toBe("문장 안 C_i \\le T_i와 따로 쓴 식\n\nU = \\sum_i C_i / T_i\n\n값은 $5 이다.");
  });

  it("코드 안의 $는 수식이 아니다", () => {
    expect(formatMathForCopy("`echo $HOME $PATH` 와 $x$", "bracket")).toBe("`echo $HOME $PATH` 와 \\(x\\)");
  });
});

describe("wrapMath (추정 표기)", () => {
  it("구분 기호로 감싼다", () => {
    expect(wrapMath("f^j_k", "dollar")).toBe("$f^j_k$");
    expect(wrapMath("f^j_k", "bracket")).toBe("\\(f^j_k\\)");
    expect(wrapMath("f^j_k", "none")).toBe("f^j_k");
  });

  it("문장 속 추정 표기는 첨자·분수 토막만 감싸고 문장부호는 밖에 둔다", () => {
    const quote = "the bound C_k, holds when (x^2 + \\frac{a + 1}{b}).";
    expect(wrapMath(quote, "dollar")).toBe("the bound $C_k$, holds when ($x^2$ + $\\frac{a + 1}{b}$).");
    expect(wrapMath(quote, "bracket")).toBe("the bound \\(C_k\\), holds when (\\(x^2\\) + \\(\\frac{a + 1}{b}\\)).");
    expect(wrapMath(quote, "none")).toBe(quote);
  });
});
