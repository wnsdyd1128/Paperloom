/**
 * 아티팩트의 미리 보기 문서(격리 iframe의 srcdoc)를 만든다. Mermaid는 웹앱에서 SVG로 그리고(securityLevel strict),
 * React는 sucrase로 JSX·TypeScript·import를 바꾼 뒤 React 묶음과 함께 넣는다. 두 라이브러리와 React 묶음은 그 종류를
 * 처음 열 때만 불러온다. markdown·code는 iframe 없이 창이 직접 그리므로 여기서 다루지 않는다.
 */
import type { Artifact } from "./artifact";
import { htmlDocument, reactDocument, svgDocument } from "./frameDocument";
import runtimeUrl from "./reactRuntime.ts?worker&url";

export type FramedArtifact = Artifact & Readonly<{ type: "html" | "svg" | "mermaid" | "react" }>;

export function isFramed(artifact: Artifact): artifact is FramedArtifact {
  return artifact.type === "html" || artifact.type === "svg" || artifact.type === "mermaid" || artifact.type === "react";
}

let runtime: Promise<string> | null = null;
let mermaidCount = 0;

/** 미리 보기 문서. 그리지 못하면 이유를 담은 Error를 던진다. */
export async function previewDocument(artifact: FramedArtifact): Promise<string> {
  if (artifact.type === "html") return htmlDocument(artifact.content);
  if (artifact.type === "svg") return svgDocument(artifact.content);
  if (artifact.type === "mermaid") {
    const { default: mermaid } = await import("mermaid");
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "default" });
    // 그리는 동안 웹앱 문서에 잠깐 놓이므로 겹치지 않는 id로 그리고, 결과에서는 고정 이름으로 바꾼다. 같은 그림은 같은 문서가
    // 되어 링크도 같다(standalone.ts)
    const id = `artifact-mermaid-${++mermaidCount}`;
    try {
      const { svg } = await mermaid.render(id, artifact.content);
      return svgDocument(svg.replaceAll(id, "artifact-mermaid"));
    } catch (error) {
      throw new Error(`Mermaid 문법을 읽지 못했습니다: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  const { transform } = await import("sucrase");
  let compiled: string;
  try {
    compiled = transform(artifact.content, { transforms: ["jsx", "typescript", "imports"], jsxRuntime: "classic", production: true }).code;
  } catch (error) {
    throw new Error(`React 코드를 읽지 못했습니다: ${error instanceof Error ? error.message : String(error)}`);
  }
  runtime ??= fetch(runtimeUrl).then((response) => {
    if (!response.ok) throw new Error("React 실행 파일을 불러오지 못했습니다.");
    return response.text();
  });
  try {
    return reactDocument(await runtime, compiled);
  } catch (error) {
    runtime = null; // 다음에 다시 받아 본다
    throw error;
  }
}
