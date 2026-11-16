/**
 * 답을 만드는 중(streaming)에만 쓰는 rehype 플러그인. 글을 낱말마다 <span class="stream-word">로 감싸, 새로 온
 * 낱말이 하나씩 아래에서 올라오며 흐림이 걷히게 한다(Motion Studies "Streaming Reply", chat/StreamingAnswer.tsx).
 * 수식(KaTeX)·코드·SVG 안의 글은 모양이 깨지지 않도록 감싸지 않는다. 낱말 사이 빈칸은 글자 그대로 두어 줄은 빈칸에서 바뀐다.
 */
type HastNode = {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
};

const KEEP_WHOLE = new Set(["code", "pre", "svg", "math", "script", "style"]);

function keepWhole(node: HastNode): boolean {
  if (node.tagName && KEEP_WHOLE.has(node.tagName)) return true;
  const classes = node.properties?.className;
  return Array.isArray(classes) && classes.some((name) => String(name).startsWith("katex"));
}

function words(value: string): HastNode[] {
  return value
    .split(/(\s+)/)
    .filter((part) => part !== "")
    .map((part) =>
      /^\s+$/.test(part)
        ? { type: "text", value: part }
        : { type: "element", tagName: "span", properties: { className: ["stream-word"] }, children: [{ type: "text", value: part }] },
    );
}

function wrap(children: HastNode[]): HastNode[] {
  return children.flatMap((child) => {
    if (child.type === "text") return words(child.value ?? "");
    if (child.type === "element" && child.children && !keepWhole(child)) child.children = wrap(child.children);
    return [child];
  });
}

export function rehypeStreamWords() {
  return (tree: HastNode) => {
    if (tree.children) tree.children = wrap(tree.children);
  };
}
