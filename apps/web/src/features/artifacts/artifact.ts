/**
 * Claude가 답에 쓰는 아티팩트 (2026-11-08 사용자 요청: claude.ai의 artifact처럼). 답 Markdown의 울타리 코드 블록이다:
 *
 *     ```artifact type="html" title="캐시 간섭 시각화"
 *     <!doctype html>…
 *     ```
 *
 * 형식은 브리지의 시스템 프롬프트(backend/src/paperloom/integrations/claude_code/cli.py)가 정한다. 답과 함께 저장되므로
 * 다시 열어도 남고, 다른 곳에 붙여 넣으면 보통 코드 블록으로 보인다. 그리는 곳은 Reader 본문 위 창(ArtifactWindow)이다. Reader 오른쪽의 아티팩트 탭(ArtifactPanel)은
 * 이 논문 대화의 아티팩트를 모아 보이며, 서버가 같은 규칙으로 찾는다(backend/src/paperloom/artifacts/blocks.py).
 */

export const ARTIFACT_TYPES = ["html", "svg", "mermaid", "react", "markdown", "code"] as const;
export type ArtifactType = (typeof ARTIFACT_TYPES)[number];

export type Artifact = Readonly<{
  type: ArtifactType;
  title: string;
  /** code의 언어(python 등). 다른 종류는 null */
  language: string | null;
  content: string;
}>;

export const ARTIFACT_LANGUAGE = "artifact"; // 울타리 코드 블록의 언어

export const ARTIFACT_LABELS: Readonly<Record<ArtifactType, string>> = {
  html: "HTML",
  svg: "SVG 그림",
  mermaid: "다이어그램",
  react: "React",
  markdown: "문서",
  code: "코드",
};

const DEFAULT_TITLES: Readonly<Record<ArtifactType, string>> = {
  html: "HTML 페이지",
  svg: "그림",
  mermaid: "다이어그램",
  react: "React 화면",
  markdown: "문서",
  code: "코드",
};

/**
 * 울타리 줄의 언어 뒤 글(meta)에서 type·title·language를 읽는다(`key="값"`). type이 없거나 모르는 값이면 null이다
 * (그 블록은 보통 코드 블록으로 보인다).
 */
export function parseArtifact(meta: string | null | undefined, content: string): Artifact | null {
  const fields = new Map([...(meta ?? "").matchAll(/(\w+)="([^"]*)"/g)].map(([, key, value]) => [key, value.trim()]));
  const type = fields.get("type") as ArtifactType | undefined;
  if (!type || !ARTIFACT_TYPES.includes(type)) return null;
  return {
    type,
    title: fields.get("title") || DEFAULT_TITLES[type],
    language: type === "code" ? (fields.get("language") || null) : null,
    content: content.replace(/\n$/, ""),
  };
}

/**
 * 아티팩트 형식이 아닌 울타리 블록 가운데 그대로 열 수 있는 것: html의 완전한 문서(<!doctype html>이나 <html>로 시작),
 * svg의 <svg> 요소, mermaid 블록. 2026-11-08 Sonnet이 "claude artifact로 만들어줘"에 ```html 블록으로 답했는데, 그런 답도
 * 열 수 있게 한다. 그 밖(조각 HTML·다른 언어)은 null이다(보통 코드 블록으로 보인다).
 */
export function fencedArtifact(language: string, content: string): Artifact | null {
  const text = content.replace(/\n$/, "");
  const start = text.trimStart().slice(0, 32).toLowerCase();
  const kind = language.toLowerCase();
  if (kind === "html" && (start.startsWith("<!doctype html") || /^<html[\s>]/.test(start))) {
    const title = /<title[^>]*>([^<]*)<\/title>/i.exec(text)?.[1]?.trim();
    return { type: "html", title: title || DEFAULT_TITLES.html, language: null, content: text };
  }
  if (kind === "svg" && /^<svg[\s>]/.test(start)) return { type: "svg", title: DEFAULT_TITLES.svg, language: null, content: text };
  if (kind === "mermaid" && text.trim()) return { type: "mermaid", title: DEFAULT_TITLES.mermaid, language: null, content: text };
  return null;
}

const CODE_EXTENSIONS: Readonly<Record<string, string>> = {
  python: "py",
  py: "py",
  javascript: "js",
  js: "js",
  typescript: "ts",
  ts: "ts",
  tsx: "tsx",
  jsx: "jsx",
  c: "c",
  cpp: "cpp",
  "c++": "cpp",
  java: "java",
  rust: "rs",
  go: "go",
  bash: "sh",
  sh: "sh",
  shell: "sh",
  powershell: "ps1",
  r: "r",
  matlab: "m",
  julia: "jl",
  sql: "sql",
  json: "json",
  yaml: "yaml",
  latex: "tex",
  tex: "tex",
  css: "css",
  html: "html",
};

const TYPE_EXTENSIONS: Readonly<Record<Exclude<ArtifactType, "code">, string>> = {
  html: "html",
  svg: "svg",
  mermaid: "mmd",
  react: "jsx",
  markdown: "md",
};

/** 내려받을 파일 이름: 제목(파일 이름에 못 쓰는 글자는 _) + 종류에 맞는 확장자 */
export function artifactFileName(artifact: Artifact): string {
  const base = artifact.title.replace(/[\\/:*?"<>|\u0000-\u001f]+/g, "_").trim() || DEFAULT_TITLES[artifact.type];
  const extension =
    artifact.type === "code" ? (CODE_EXTENSIONS[(artifact.language ?? "").toLowerCase()] ?? "txt") : TYPE_EXTENSIONS[artifact.type];
  return `${base}.${extension}`;
}

/** 내려받을 파일의 MIME 형식 */
export function artifactMimeType(artifact: Artifact): string {
  if (artifact.type === "html") return "text/html;charset=utf-8";
  if (artifact.type === "svg") return "image/svg+xml;charset=utf-8";
  if (artifact.type === "markdown") return "text/markdown;charset=utf-8";
  return "text/plain;charset=utf-8";
}
