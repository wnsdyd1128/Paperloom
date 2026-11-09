/**
 * 링크로 여는 아티팩트 페이지 (2026-11-08 사용자 요청: claude.ai 링크 대신 이 PC의 파일과 링크). Core가 이 문서를 파일로 쓰고
 * /artifacts/<id>에서 격리해서 준다(backend paperloom/artifacts). 창의 격리 문서(preview.ts)에 탭 제목을 붙인 것이고, 문서는
 * 답과 같은 Markdown으로 그린 HTML을, 코드는 글자 그대로를 담는다. 필요한 것(React 묶음 포함)이 문서 하나에 다 들어 있다.
 */
import { createElement } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";

import { AnswerMarkdown } from "../answers/AnswerMarkdown";
import type { Artifact } from "./artifact";
import { codeDocument, markdownDocument, withTitle } from "./frameDocument";
import { type FigureImages, withFigureImages } from "./paperFigures";
import { isFramed, previewDocument } from "./preview";

/** 페이지 문서. figures는 논문 그림 참조의 그림이다(paperFigures.ts). 그리지 못하면(Mermaid·React 문법 등) 이유를 담은 Error를 던진다. */
export async function standaloneDocument(artifact: Artifact, figures: FigureImages = new Map()): Promise<string> {
  const document = isFramed(artifact)
    ? await previewDocument({ ...artifact, content: withFigureImages(artifact.content, figures) })
    : artifact.type === "markdown"
      ? markdownDocument(renderMarkdown(artifact.content, figures))
      : codeDocument(artifact.content);
  return withTitle(document, artifact.title);
}

/** 창에서 보이는 것과 같은 Markdown을 화면 밖에서 그려 HTML로 꺼낸다 */
function renderMarkdown(markdown: string, figures: FigureImages): string {
  const container = window.document.createElement("div");
  const root = createRoot(container);
  flushSync(() => root.render(createElement(AnswerMarkdown, { markdown, canCite: () => false, onCite: () => undefined, figures })));
  const html = container.innerHTML;
  root.unmount();
  return html;
}
