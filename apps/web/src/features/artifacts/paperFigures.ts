/**
 * 아티팩트 안의 논문 원본 그림 (2026-11-09 사용자 요청: "논문의 발표 슬라이드에서 논문에서 사용한 figure도 같이 첨부해서
 * 만들어줘"). Claude는 그림을 옮겨 적지 못하고 격리 문서는 바깥 주소를 불러오지 못하므로(frameDocument.ts의 CSP), Claude는
 * 그림 번호로 `paperloom-figure:3`을 이미지 주소로 쓰고(브리지 규칙, backend integrations/claude_code/cli.py), 창은 그리기 전에
 * 그 주소를 Core가 원문에서 잘라 그린 PNG의 data: URL로 바꾼다(backend reading/numbered_figures.py). CSP가 data: 이미지를
 * 허용하므로 그림이 문서 안에 들어간다. 찾지 못한 그림은 그 사실을 적은 자리 그림이 된다.
 * 번호는 지금 보고 있는 판본에서 찾는다(답을 만든 판본과 다를 수 있다).
 */

export const FIGURE_SCHEME = "paperloom-figure:";
const REFERENCE = /paperloom-figure:([A-Za-z]?\d+)(?!\w)/g;
const SCALE = 2; // 슬라이드에 크게 보여도 흐리지 않게

/** 참조("paperloom-figure:3") → 그림의 data: URL(찾지 못했으면 자리 그림) */
export type FigureImages = ReadonlyMap<string, string>;

/** 아티팩트 글의 그림 참조(나온 차례, 겹치지 않게) */
export function figureReferences(content: string): string[] {
  return [...new Set(Array.from(content.matchAll(REFERENCE), (match) => match[0]))];
}

/** 그림 참조를 그림으로 바꾼 글. images에 없는 참조는 그대로 둔다 */
export function withFigureImages(content: string, images: FigureImages): string {
  return images.size === 0 ? content : content.replace(REFERENCE, (reference) => images.get(reference) ?? reference);
}

/** 글의 그림 참조마다 그림을 받는다. 실패하지 않는다: 받지 못한 그림(판본을 모름, 없는 번호, 연결 실패)은 자리 그림이다 */
export async function loadFigureImages(versionId: string | null, content: string): Promise<FigureImages> {
  const references = figureReferences(content);
  const images = await Promise.all(references.map((reference) => figureImage(versionId, reference.slice(FIGURE_SCHEME.length))));
  return new Map(references.map((reference, index) => [reference, images[index]]));
}

async function figureImage(versionId: string | null, label: string): Promise<string> {
  if (versionId === null) return missingFigure(label);
  try {
    const response = await fetch(`/api/v1/versions/${encodeURIComponent(versionId)}/figures/${encodeURIComponent(label)}/image?scale=${SCALE}`);
    if (!response.ok) return missingFigure(label);
    return await dataUrl(await response.blob());
  } catch {
    return missingFigure(label);
  }
}

async function dataUrl(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let start = 0; start < bytes.length; start += 0x8000) binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
  return `data:${blob.type || "image/png"};base64,${btoa(binary)}`;
}

/** 찾지 못한 그림의 자리(SVG). 번호는 [A-Za-z]?\d+뿐이라 그대로 넣어도 된다 */
export function missingFigure(label: string): string {
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="160" viewBox="0 0 480 160">' +
    '<rect x="1" y="1" width="478" height="158" fill="#f5f5f4" stroke="#a8a29e" stroke-dasharray="6 4"/>' +
    `<text x="240" y="76" text-anchor="middle" font-family="system-ui,sans-serif" font-size="16" fill="#57534e">Figure ${label}</text>` +
    '<text x="240" y="102" text-anchor="middle" font-family="system-ui,sans-serif" font-size="13" fill="#78716c">원문에서 이 그림을 찾지 못했습니다</text>' +
    "</svg>";
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
