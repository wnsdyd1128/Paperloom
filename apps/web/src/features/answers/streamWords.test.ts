import { describe, expect, it } from "vitest";

import { rehypeStreamWords } from "./streamWords";

type Node = { type: string; tagName?: string; value?: string; properties?: Record<string, unknown>; children?: Node[] };

const text = (value: string): Node => ({ type: "text", value });
const element = (tagName: string, children: Node[], className?: string[]): Node => ({
  type: "element",
  tagName,
  properties: className ? { className } : {},
  children,
});

/** 감싼 낱말과 남은 글을 순서대로 적는다: 낱말은 [낱말], 빈칸은 그대로 */
function flatten(node: Node): string {
  if (node.type === "text") return node.value ?? "";
  if (node.tagName === "span" && (node.properties?.className as string[] | undefined)?.includes("stream-word")) {
    return `[${(node.children ?? []).map(flatten).join("")}]`;
  }
  return (node.children ?? []).map(flatten).join("");
}

function run(tree: Node) {
  rehypeStreamWords()(tree);
  return tree;
}

describe("rehypeStreamWords (답을 만드는 중의 낱말)", () => {
  it("문단·강조 안의 글을 낱말마다 감싸고 빈칸은 글자로 둔다", () => {
    const tree = run({ type: "root", children: [element("p", [text("캐시 친화성 "), element("strong", [text("스케줄링")]), text(" 실험\n결과")])] });
    expect(flatten(tree)).toBe("[캐시] [친화성] [스케줄링] [실험]\n[결과]");
  });

  it("수식(KaTeX)·코드는 감싸지 않는다", () => {
    const math = element("span", [element("span", [text("C i ≤ T i")], ["katex-html"])], ["katex"]);
    const code = element("pre", [element("code", [text("let x = 1")])]);
    const tree = run({ type: "root", children: [element("p", [text("식 "), math]), code] });
    expect(flatten(tree)).toBe("[식] C i ≤ T ilet x = 1");
  });
});
